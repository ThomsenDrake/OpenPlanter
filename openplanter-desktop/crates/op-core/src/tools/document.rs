use std::collections::HashSet;
use std::path::{Path, PathBuf};
use std::time::Duration;

use base64::{engine::general_purpose::STANDARD, Engine as _};
use serde_json::{json, Map, Value};

use super::{filesystem, ToolResult};

const DOCUMENT_PDF_EXTENSIONS: &[&str] = &[".pdf"];
const DOCUMENT_IMAGE_EXTENSIONS: &[&str] = &[".avif", ".jpg", ".jpeg", ".png", ".webp"];

fn rel_path(root: &Path, path: &Path) -> String {
    let canon_root = std::fs::canonicalize(root).unwrap_or_else(|_| root.to_path_buf());
    path.strip_prefix(&canon_root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}

fn ocr_endpoint(base_url: &str) -> String {
    let trimmed = base_url.trim().trim_end_matches('/');
    if trimmed.ends_with("/v1") {
        format!("{trimmed}/ocr")
    } else {
        format!("{trimmed}/v1/ocr")
    }
}

fn chat_endpoint(base_url: &str) -> String {
    let trimmed = base_url.trim().trim_end_matches('/');
    if trimmed.ends_with("/v1") {
        format!("{trimmed}/chat/completions")
    } else {
        format!("{trimmed}/v1/chat/completions")
    }
}

fn effective_document_ai_key<'a>(
    shared_api_key: Option<&'a str>,
    override_api_key: Option<&'a str>,
    use_shared_key: bool,
) -> Result<&'a str, String> {
    let key = if use_shared_key {
        shared_api_key
    } else {
        override_api_key
    }
    .map(str::trim)
    .filter(|value| !value.is_empty());

    if let Some(value) = key {
        return Ok(value);
    }

    if use_shared_key {
        Err("Mistral Document AI shared key not configured. Set OPENPLANTER_MISTRAL_API_KEY or MISTRAL_API_KEY.".into())
    } else {
        Err("Mistral Document AI override key not configured. Set OPENPLANTER_MISTRAL_DOCUMENT_AI_API_KEY or MISTRAL_DOCUMENT_AI_API_KEY, or switch to shared key mode.".into())
    }
}

fn document_media_type(path: &Path) -> &'static str {
    match path
        .extension()
        .and_then(|value| value.to_str())
        .map(|value| value.to_ascii_lowercase())
        .as_deref()
    {
        Some("avif") => "image/avif",
        Some("jpg") | Some("jpeg") => "image/jpeg",
        Some("pdf") => "application/pdf",
        Some("png") => "image/png",
        Some("webp") => "image/webp",
        _ => "application/octet-stream",
    }
}

fn is_pdf_extension(ext: &str) -> bool {
    DOCUMENT_PDF_EXTENSIONS.iter().any(|value| *value == ext)
}

fn is_ocr_extension(ext: &str) -> bool {
    is_pdf_extension(ext) || DOCUMENT_IMAGE_EXTENSIONS.iter().any(|value| *value == ext)
}

fn normalize_pages(pages: Option<&[i64]>) -> Result<Option<Vec<i64>>, String> {
    let Some(pages) = pages else {
        return Ok(None);
    };
    let mut normalized = Vec::new();
    for page in pages {
        if *page < 0 {
            return Err("pages must contain only non-negative integers".into());
        }
        if !normalized.contains(page) {
            normalized.push(*page);
        }
    }
    Ok((!normalized.is_empty()).then_some(normalized))
}

fn build_data_url(
    resolved: &Path,
    max_bytes: usize,
) -> Result<(String, String, String, usize), String> {
    let ext = resolved
        .extension()
        .and_then(|value| value.to_str())
        .map(|value| format!(".{}", value.to_ascii_lowercase()))
        .unwrap_or_default();
    if !is_ocr_extension(&ext) {
        let mut supported: Vec<&str> = DOCUMENT_PDF_EXTENSIONS.iter().copied().collect();
        supported.extend(DOCUMENT_IMAGE_EXTENSIONS.iter().copied());
        supported.sort_unstable();
        return Err(format!(
            "Unsupported document format: {}. Supported: {}",
            if ext.is_empty() { "(none)" } else { &ext },
            supported.join(", ")
        ));
    }
    let metadata = std::fs::metadata(resolved).map_err(|error| {
        format!(
            "Failed to inspect document file {}: {error}",
            resolved.display()
        )
    })?;
    if metadata.len() as usize > max_bytes {
        return Err(format!(
            "Document file too large: {} bytes (max {} bytes)",
            metadata.len(),
            max_bytes
        ));
    }
    let bytes = std::fs::read(resolved).map_err(|error| {
        format!(
            "Failed to read document file {}: {error}",
            resolved.display()
        )
    })?;
    let media_type = document_media_type(resolved).to_string();
    let data_url = format!("data:{};base64,{}", media_type, STANDARD.encode(bytes));
    let source_type = if DOCUMENT_IMAGE_EXTENSIONS.iter().any(|value| *value == ext) {
        "image_url"
    } else {
        "document_url"
    };
    Ok((
        data_url,
        source_type.to_string(),
        media_type,
        metadata.len() as usize,
    ))
}

fn build_response_format(schema: &Value, name: &str) -> Value {
    if let Some(schema_type) = schema.get("type").and_then(Value::as_str) {
        if schema_type == "json_schema" && schema.get("json_schema").is_some() {
            return schema.clone();
        }
        if schema_type == "text" || schema_type == "json_object" {
            return schema.clone();
        }
    }
    json!({
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "schema": schema,
        }
    })
}

fn json_length(payload: &Value) -> usize {
    serde_json::to_string_pretty(payload)
        .unwrap_or_else(|_| payload.to_string())
        .len()
}

fn is_empty_value(value: &Value) -> bool {
    match value {
        Value::Null => true,
        Value::String(text) => text.is_empty(),
        Value::Array(items) => items.is_empty(),
        Value::Object(map) => map.is_empty(),
        _ => false,
    }
}

fn note_omitted_field(truncation: &mut Map<String, Value>, label: &str, value: &Value) {
    match value {
        Value::Array(items) => {
            truncation.insert(format!("omitted_{label}_items"), json!(items.len()));
        }
        Value::Object(map) => {
            truncation.insert(format!("omitted_{label}_keys"), json!(map.len()));
        }
        Value::String(text) => {
            truncation.insert(format!("omitted_{label}_chars"), json!(text.len()));
        }
        other => {
            truncation.insert(
                format!("omitted_{label}_type"),
                Value::String(other_type_name(other).to_string()),
            );
        }
    }
    if let Ok(serialized) = serde_json::to_string(value) {
        truncation.insert(
            format!("omitted_{label}_json_chars"),
            json!(serialized.len()),
        );
    }
}

fn other_type_name(value: &Value) -> &'static str {
    match value {
        Value::Null => "null",
        Value::Bool(_) => "bool",
        Value::Number(_) => "number",
        Value::String(_) => "string",
        Value::Array(_) => "array",
        Value::Object(_) => "object",
    }
}

fn omit_payload_field(payload: &mut Value, field: &str, label: &str) -> bool {
    let removed = {
        let Some(object) = payload.as_object_mut() else {
            return false;
        };
        object.remove(field)
    };
    let Some(value) = removed else {
        return false;
    };
    if !is_empty_value(&value) {
        if let Some(truncation) = payload.get_mut("truncation").and_then(Value::as_object_mut) {
            note_omitted_field(truncation, label, &value);
        }
    }
    true
}

fn omit_response_field(payload: &mut Value, field: &str, label: &str) -> bool {
    let removed = {
        let Some(response) = payload.get_mut("response").and_then(Value::as_object_mut) else {
            return false;
        };
        response.remove(field)
    };
    let Some(value) = removed else {
        return false;
    };
    if !is_empty_value(&value) {
        if let Some(truncation) = payload.get_mut("truncation").and_then(Value::as_object_mut) {
            note_omitted_field(truncation, label, &value);
        }
    }
    true
}

fn coerce_jsonish_value(value: &Value) -> Value {
    if let Some(text) = value.as_str() {
        let trimmed = text.trim();
        if trimmed.starts_with('{') || trimmed.starts_with('[') {
            if let Ok(parsed) = serde_json::from_str::<Value>(trimmed) {
                return parsed;
            }
        }
    }
    value.clone()
}

fn collect_document_text(parsed: &Value) -> String {
    parsed
        .get("pages")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|page| page.get("markdown").and_then(Value::as_str))
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .collect::<Vec<_>>()
        .join("\n\n")
}

fn document_pages_suffix(pages: Option<&[i64]>) -> String {
    let Some(pages) = pages else {
        return String::new();
    };
    if pages.is_empty() {
        return String::new();
    }
    let mut one_based: Vec<i64> = pages.iter().map(|page| page + 1).collect();
    one_based.sort_unstable();
    let mut segments = Vec::new();
    let mut start = one_based[0];
    let mut end = start;
    for page in one_based.into_iter().skip(1) {
        if page == end + 1 {
            end = page;
            continue;
        }
        if start == end {
            segments.push(start.to_string());
        } else {
            segments.push(format!("{start}-{end}"));
        }
        start = page;
        end = page;
    }
    if start == end {
        segments.push(start.to_string());
    } else {
        segments.push(format!("{start}-{end}"));
    }
    format!(".pages-{}", segments.join("_"))
}

fn document_ocr_sidecar_paths(resolved: &Path, pages: Option<&[i64]>) -> (PathBuf, PathBuf) {
    let base_name = format!(
        "{}.ocr{}",
        resolved.file_name().unwrap_or_default().to_string_lossy(),
        document_pages_suffix(pages)
    );
    (
        resolved.with_file_name(format!("{base_name}.md")),
        resolved.with_file_name(format!("{base_name}.json")),
    )
}

fn strip_document_image_base64(value: &mut Value) {
    match value {
        Value::Object(map) => {
            map.remove("image_base64");
            for child in map.values_mut() {
                strip_document_image_base64(child);
            }
        }
        Value::Array(items) => {
            for child in items {
                strip_document_image_base64(child);
            }
        }
        _ => {}
    }
}

fn render_document_ocr_markdown(
    rel_source_path: &str,
    model: &str,
    pages: Option<&[i64]>,
    parsed: &Value,
    json_rel_path: &str,
) -> String {
    let page_label = pages
        .map(|values| {
            values
                .iter()
                .map(|page| (page + 1).to_string())
                .collect::<Vec<_>>()
                .join(", ")
        })
        .filter(|label| !label.is_empty())
        .unwrap_or_else(|| "all".to_string());
    let mut lines = vec![
        "<!-- OpenPlanter document_ocr artifact -->".to_string(),
        format!("<!-- source: {rel_source_path} -->"),
        format!("<!-- model: {model} -->"),
        format!("<!-- pages: {page_label} -->"),
        format!("<!-- json_sidecar: {json_rel_path} -->"),
        String::new(),
    ];

    let mut appended_page = false;
    if let Some(raw_pages) = parsed.get("pages").and_then(Value::as_array) {
        for (fallback_index, page) in raw_pages.iter().enumerate() {
            let Some(markdown) = page.get("markdown").and_then(Value::as_str) else {
                continue;
            };
            let markdown = markdown.trim();
            if markdown.is_empty() {
                continue;
            }
            let page_number = page
                .get("index")
                .and_then(Value::as_i64)
                .filter(|index| *index >= 0)
                .map(|index| index + 1)
                .unwrap_or((fallback_index + 1) as i64);
            lines.push(format!("## Page {page_number}"));
            lines.push(String::new());
            lines.push(markdown.to_string());
            lines.push(String::new());
            appended_page = true;
        }
    }

    if !appended_page {
        let text = collect_document_text(parsed);
        if text.trim().is_empty() {
            lines.push("<!-- no OCR text returned -->".to_string());
            lines.push(String::new());
        } else {
            lines.push(text);
            lines.push(String::new());
        }
    }

    lines.join("\n")
}

fn write_document_ocr_sidecars(
    root: &Path,
    resolved: &Path,
    media_type: &str,
    size_bytes: usize,
    source_type: &str,
    model: &str,
    include_images: bool,
    pages: Option<&[i64]>,
    text: &str,
    parsed: &Value,
) -> Result<Value, String> {
    let (markdown_path, json_path) = document_ocr_sidecar_paths(resolved, pages);
    if let Some(parent) = markdown_path.parent() {
        std::fs::create_dir_all(parent).map_err(|error| {
            format!(
                "Failed to prepare OCR sidecar directory {}: {error}",
                parent.display()
            )
        })?;
    }
    let markdown_rel = rel_path(root, &markdown_path);
    let json_rel = rel_path(root, &json_path);
    let artifacts = json!({
        "markdown_path": markdown_rel,
        "json_path": json_rel,
    });

    let mut response_copy = parsed.clone();
    strip_document_image_base64(&mut response_copy);
    let sidecar_envelope = json!({
        "provider": "mistral",
        "service": "document_ai",
        "operation": "ocr",
        "path": rel_path(root, resolved),
        "file": {
            "media_type": media_type,
            "size_bytes": size_bytes,
            "source_type": source_type,
        },
        "model": model,
        "options": {
            "include_images": include_images,
            "pages": pages,
        },
        "artifacts": artifacts,
        "text": text,
        "response": response_copy,
    });
    let markdown = render_document_ocr_markdown(
        &rel_path(root, resolved),
        model,
        pages,
        parsed,
        sidecar_envelope["artifacts"]["json_path"]
            .as_str()
            .unwrap_or_default(),
    );
    std::fs::write(&markdown_path, markdown).map_err(|error| {
        format!(
            "Failed to write OCR markdown sidecar {}: {error}",
            markdown_path.display()
        )
    })?;
    let json_text = serde_json::to_string_pretty(&sidecar_envelope)
        .map_err(|error| format!("Failed to serialize OCR sidecar JSON: {error}"))?;
    std::fs::write(&json_path, json_text).map_err(|error| {
        format!(
            "Failed to write OCR JSON sidecar {}: {error}",
            json_path.display()
        )
    })?;
    Ok(artifacts)
}

fn collect_bbox_annotations(parsed: &Value) -> Vec<Value> {
    let mut out = Vec::new();
    let Some(pages) = parsed.get("pages").and_then(Value::as_array) else {
        return out;
    };
    for page in pages {
        let page_index = page.get("index").cloned().unwrap_or(Value::Null);
        let Some(images) = page.get("images").and_then(Value::as_array) else {
            continue;
        };
        for (image_index, image) in images.iter().enumerate() {
            let Some(annotation) = image.get("bbox_annotation") else {
                continue;
            };
            let mut entry = Map::new();
            entry.insert("page_index".into(), page_index.clone());
            entry.insert("image_index".into(), json!(image_index));
            entry.insert("bbox_annotation".into(), coerce_jsonish_value(annotation));
            for field in [
                "id",
                "top_left_x",
                "top_left_y",
                "bottom_right_x",
                "bottom_right_y",
            ] {
                if let Some(value) = image.get(field) {
                    entry.insert(field.into(), value.clone());
                }
            }
            out.push(Value::Object(entry));
        }
    }
    out
}

fn extract_chat_text(parsed: &Value) -> String {
    let Some(choice) = parsed
        .get("choices")
        .and_then(Value::as_array)
        .and_then(|choices| choices.first())
    else {
        return String::new();
    };
    let Some(message) = choice.get("message") else {
        return String::new();
    };
    if let Some(content) = message.get("content").and_then(Value::as_str) {
        return content.trim().to_string();
    }
    message
        .get("content")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter(|item| item.get("type").and_then(Value::as_str) == Some("text"))
        .filter_map(|item| item.get("text").and_then(Value::as_str))
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .collect::<Vec<_>>()
        .join("\n\n")
}

fn truncate_text(payload: &mut Value, max_chars: usize) {
    let original = payload
        .get("text")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string();
    if original.is_empty() {
        return;
    }
    let mut base = payload.clone();
    base["text"] = Value::String(String::new());
    if json_length(&base) > max_chars {
        payload["text"] = Value::String(String::new());
        payload["truncation"]["text_truncated_chars"] = json!(original.len());
        return;
    }

    let mut low = 0usize;
    let mut high = original.len();
    while low < high {
        let mid = (low + high + 1) / 2;
        let idx = original.floor_char_boundary(mid);
        base["text"] = Value::String(original[..idx].to_string());
        if json_length(&base) <= max_chars {
            low = idx;
        } else if idx == 0 {
            high = 0;
        } else {
            high = idx - 1;
        }
    }
    let final_idx = original.floor_char_boundary(low);
    payload["text"] = Value::String(original[..final_idx].to_string());
    let omitted = original.len().saturating_sub(final_idx);
    if omitted > 0 {
        payload["truncation"]["text_truncated_chars"] = json!(omitted);
    }
}

fn compact_truncation(payload: &mut Value) {
    let detail_count = payload
        .get("truncation")
        .and_then(Value::as_object)
        .map(|truncation| {
            truncation
                .keys()
                .filter(|key| key.as_str() != "applied")
                .count()
        })
        .unwrap_or(0);
    payload["truncation"] = json!({
        "applied": payload["truncation"]["applied"].as_bool().unwrap_or(false),
        "details_omitted": detail_count,
    });
}

fn strip_image_base64(response: &mut Value) -> usize {
    let mut omitted = 0usize;
    let Some(pages) = response.get_mut("pages").and_then(Value::as_array_mut) else {
        return omitted;
    };
    for page in pages {
        let Some(images) = page.get_mut("images").and_then(Value::as_array_mut) else {
            continue;
        };
        for image in images {
            if let Some(object) = image.as_object_mut() {
                if object.remove("image_base64").is_some() {
                    omitted += 1;
                }
            }
        }
    }
    omitted
}

fn summarize_pages(response: &mut Value) -> usize {
    let Some(pages) = response.get_mut("pages").and_then(Value::as_array_mut) else {
        return 0;
    };
    let original_count = pages.len();
    let summaries = pages
        .iter()
        .filter_map(Value::as_object)
        .map(|page| {
            json!({
                "index": page.get("index").cloned().unwrap_or(Value::Null),
                "markdown_chars": page.get("markdown").and_then(Value::as_str).map(str::len).unwrap_or(0),
                "image_count": page.get("images").and_then(Value::as_array).map(|items| items.len()).unwrap_or(0),
                "table_count": page.get("tables").and_then(Value::as_array).map(|items| items.len()).unwrap_or(0),
                "hyperlink_count": page.get("hyperlinks").and_then(Value::as_array).map(|items| items.len()).unwrap_or(0),
            })
        })
        .collect::<Vec<_>>();
    *pages = summaries;
    original_count
}

fn serialize_document_envelope(mut payload: Value, max_chars: usize) -> String {
    if payload.get("truncation").is_none() {
        payload["truncation"] = json!({"applied": false});
    }
    if json_length(&payload) <= max_chars {
        return serde_json::to_string_pretty(&payload).unwrap_or_else(|_| payload.to_string());
    }

    payload["truncation"]["applied"] = Value::Bool(true);
    let omitted_images = if let Some(response) = payload.get_mut("response") {
        strip_image_base64(response)
    } else {
        0
    };
    if omitted_images > 0 {
        payload["truncation"]["omitted_image_base64_entries"] = json!(omitted_images);
    }

    if json_length(&payload) > max_chars {
        let summarized = if let Some(response) = payload.get_mut("response") {
            summarize_pages(response)
        } else {
            0
        };
        if summarized > 0 {
            payload["truncation"]["pages_summarized"] = json!(summarized);
        }
    }

    if json_length(&payload) > max_chars {
        let omitted_pages = if let Some(response) = payload.get_mut("response") {
            let omitted_pages = response
                .get("pages")
                .and_then(Value::as_array)
                .map(|pages| pages.len())
                .unwrap_or(0);
            if let Some(object) = response.as_object_mut() {
                object.remove("pages");
            }
            omitted_pages
        } else {
            0
        };
        if omitted_pages > 0 {
            payload["truncation"]["omitted_response_pages"] = json!(omitted_pages);
        }
    }

    if json_length(&payload) > max_chars {
        let _ = omit_response_field(
            &mut payload,
            "document_annotation",
            "response_document_annotation",
        );
    }

    if json_length(&payload) > max_chars {
        let _ = omit_payload_field(&mut payload, "bbox_annotations", "bbox_annotations");
    }

    if json_length(&payload) > max_chars {
        let _ = omit_payload_field(&mut payload, "document_annotation", "document_annotation");
    }

    if json_length(&payload) > max_chars {
        truncate_text(&mut payload, max_chars);
    }

    if json_length(&payload) > max_chars {
        let _ = omit_payload_field(&mut payload, "response", "response");
    }

    if json_length(&payload) > max_chars {
        truncate_text(&mut payload, max_chars);
    }

    if json_length(&payload) > max_chars {
        compact_truncation(&mut payload);
    }

    if json_length(&payload) > max_chars {
        truncate_text(&mut payload, max_chars);
    }

    serde_json::to_string_pretty(&payload).unwrap_or_else(|_| payload.to_string())
}

async fn request_json(
    api_key: &str,
    url: &str,
    body: &Value,
    request_timeout_sec: u64,
    label: &str,
) -> Result<Value, String> {
    let client = reqwest::Client::new();
    let response = client
        .post(url)
        .bearer_auth(api_key)
        .timeout(Duration::from_secs(request_timeout_sec))
        .json(body)
        .send()
        .await
        .map_err(|error| format!("{label} request failed: {error}"))?;
    let status = response.status();
    let raw = response
        .text()
        .await
        .map_err(|error| format!("{label} returned unreadable body: {error}"))?;
    if !status.is_success() {
        return Err(format!(
            "{label} HTTP {}: {}",
            status.as_u16(),
            filesystem::clip(&raw, 1200)
        ));
    }
    serde_json::from_str(&raw).map_err(|error| {
        format!(
            "{label} returned non-JSON payload: {error}: {}",
            filesystem::clip(&raw, 500)
        )
    })
}

#[allow(clippy::too_many_arguments)]
pub async fn document_ocr(
    root: &Path,
    shared_api_key: Option<&str>,
    override_api_key: Option<&str>,
    use_shared_key: bool,
    base_url: &str,
    default_model: &str,
    max_bytes: usize,
    path: &str,
    include_images: Option<bool>,
    pages: Option<&[i64]>,
    model: Option<&str>,
    max_chars: usize,
    request_timeout_sec: u64,
    files_read: &mut HashSet<PathBuf>,
) -> ToolResult {
    let resolved = match filesystem::resolve_path(root, path) {
        Ok(value) => value,
        Err(error) => return ToolResult::error(error),
    };
    if !resolved.exists() {
        return ToolResult::error(format!("File not found: {path}"));
    }
    if resolved.is_dir() {
        return ToolResult::error(format!("Path is a directory, not a file: {path}"));
    }
    let ext = resolved
        .extension()
        .and_then(|value| value.to_str())
        .map(|value| format!(".{}", value.to_ascii_lowercase()))
        .unwrap_or_default();
    if !is_ocr_extension(&ext) {
        let mut supported: Vec<&str> = DOCUMENT_PDF_EXTENSIONS.iter().copied().collect();
        supported.extend(DOCUMENT_IMAGE_EXTENSIONS.iter().copied());
        supported.sort_unstable();
        return ToolResult::error(format!(
            "Unsupported document format: {}. Supported: {}",
            if ext.is_empty() { "(none)" } else { &ext },
            supported.join(", ")
        ));
    }
    let api_key = match effective_document_ai_key(shared_api_key, override_api_key, use_shared_key)
    {
        Ok(value) => value,
        Err(error) => return ToolResult::error(error),
    };
    let chosen_model = model.unwrap_or(default_model).trim();
    if chosen_model.is_empty() {
        return ToolResult::error("No Mistral Document AI OCR model configured".into());
    }
    let normalized_pages = match normalize_pages(pages) {
        Ok(value) => value,
        Err(error) => return ToolResult::error(error),
    };
    let (data_url, source_type, media_type, size_bytes) = match build_data_url(&resolved, max_bytes)
    {
        Ok(value) => value,
        Err(error) => return ToolResult::error(error),
    };
    files_read.insert(resolved.clone());

    let mut document = Map::new();
    document.insert("type".into(), Value::String(source_type.clone()));
    document.insert(source_type.clone(), Value::String(data_url));
    let mut body = Map::new();
    body.insert("model".into(), Value::String(chosen_model.to_string()));
    body.insert("document".into(), Value::Object(document));
    body.insert(
        "include_image_base64".into(),
        Value::Bool(include_images.unwrap_or(false)),
    );
    if let Some(pages) = normalized_pages.as_ref() {
        body.insert(
            "pages".into(),
            Value::Array(pages.iter().map(|page| json!(page)).collect()),
        );
    }

    let parsed = match request_json(
        api_key,
        &ocr_endpoint(base_url),
        &Value::Object(body),
        request_timeout_sec,
        "Mistral Document AI OCR",
    )
    .await
    {
        Ok(value) => value,
        Err(error) => return ToolResult::error(error),
    };

    let text = collect_document_text(&parsed);
    let artifacts = match write_document_ocr_sidecars(
        root,
        &resolved,
        &media_type,
        size_bytes,
        &source_type,
        chosen_model,
        include_images.unwrap_or(false),
        normalized_pages.as_deref(),
        &text,
        &parsed,
    ) {
        Ok(value) => value,
        Err(error) => return ToolResult::error(error),
    };

    let envelope = json!({
        "provider": "mistral",
        "service": "document_ai",
        "operation": "ocr",
        "path": rel_path(root, &resolved),
        "file": {
            "media_type": media_type,
            "size_bytes": size_bytes,
            "source_type": source_type,
        },
        "model": chosen_model,
        "options": {
            "include_images": include_images.unwrap_or(false),
            "pages": normalized_pages,
        },
        "artifacts": artifacts,
        "text": text,
        "response": parsed,
    });
    ToolResult::ok(serialize_document_envelope(envelope, max_chars))
}

#[allow(clippy::too_many_arguments)]
pub async fn document_annotations(
    root: &Path,
    shared_api_key: Option<&str>,
    override_api_key: Option<&str>,
    use_shared_key: bool,
    base_url: &str,
    default_model: &str,
    max_bytes: usize,
    path: &str,
    document_schema: Option<&Value>,
    bbox_schema: Option<&Value>,
    instruction: Option<&str>,
    include_images: Option<bool>,
    pages: Option<&[i64]>,
    model: Option<&str>,
    max_chars: usize,
    request_timeout_sec: u64,
    files_read: &mut HashSet<PathBuf>,
) -> ToolResult {
    if document_schema.is_none() && bbox_schema.is_none() {
        return ToolResult::error(
            "document_annotations requires document_schema, bbox_schema, or both".into(),
        );
    }
    if instruction.is_some() && document_schema.is_none() {
        return ToolResult::error("instruction requires document_schema".into());
    }
    let resolved = match filesystem::resolve_path(root, path) {
        Ok(value) => value,
        Err(error) => return ToolResult::error(error),
    };
    if !resolved.exists() {
        return ToolResult::error(format!("File not found: {path}"));
    }
    if resolved.is_dir() {
        return ToolResult::error(format!("Path is a directory, not a file: {path}"));
    }
    let ext = resolved
        .extension()
        .and_then(|value| value.to_str())
        .map(|value| format!(".{}", value.to_ascii_lowercase()))
        .unwrap_or_default();
    if !is_ocr_extension(&ext) {
        let mut supported: Vec<&str> = DOCUMENT_PDF_EXTENSIONS.iter().copied().collect();
        supported.extend(DOCUMENT_IMAGE_EXTENSIONS.iter().copied());
        supported.sort_unstable();
        return ToolResult::error(format!(
            "Unsupported document format: {}. Supported: {}",
            if ext.is_empty() { "(none)" } else { &ext },
            supported.join(", ")
        ));
    }
    let api_key = match effective_document_ai_key(shared_api_key, override_api_key, use_shared_key)
    {
        Ok(value) => value,
        Err(error) => return ToolResult::error(error),
    };
    let chosen_model = model.unwrap_or(default_model).trim();
    if chosen_model.is_empty() {
        return ToolResult::error("No Mistral Document AI OCR model configured".into());
    }
    let normalized_pages = match normalize_pages(pages) {
        Ok(value) => value,
        Err(error) => return ToolResult::error(error),
    };
    let (data_url, source_type, media_type, size_bytes) = match build_data_url(&resolved, max_bytes)
    {
        Ok(value) => value,
        Err(error) => return ToolResult::error(error),
    };
    files_read.insert(resolved.clone());

    let mut document = Map::new();
    document.insert("type".into(), Value::String(source_type.clone()));
    document.insert(source_type.clone(), Value::String(data_url));
    let mut body = Map::new();
    body.insert("model".into(), Value::String(chosen_model.to_string()));
    body.insert("document".into(), Value::Object(document));
    body.insert(
        "include_image_base64".into(),
        Value::Bool(include_images.unwrap_or(false)),
    );
    if let Some(pages) = normalized_pages.as_ref() {
        body.insert(
            "pages".into(),
            Value::Array(pages.iter().map(|page| json!(page)).collect()),
        );
    }
    if let Some(schema) = document_schema {
        body.insert(
            "document_annotation_format".into(),
            build_response_format(schema, "document_annotation"),
        );
    }
    if let Some(schema) = bbox_schema {
        body.insert(
            "bbox_annotation_format".into(),
            build_response_format(schema, "bbox_annotation"),
        );
    }
    if let Some(instruction) = instruction.map(str::trim).filter(|value| !value.is_empty()) {
        body.insert(
            "document_annotation_prompt".into(),
            Value::String(instruction.to_string()),
        );
    }

    let parsed = match request_json(
        api_key,
        &ocr_endpoint(base_url),
        &Value::Object(body),
        request_timeout_sec,
        "Mistral Document AI annotations",
    )
    .await
    {
        Ok(value) => value,
        Err(error) => return ToolResult::error(error),
    };

    let document_annotation = parsed
        .get("document_annotation")
        .map(coerce_jsonish_value)
        .unwrap_or(Value::Null);
    let bbox_annotations = collect_bbox_annotations(&parsed);
    let text = if !document_annotation.is_null() {
        serde_json::to_string_pretty(&document_annotation)
            .unwrap_or_else(|_| document_annotation.to_string())
    } else if !bbox_annotations.is_empty() {
        serde_json::to_string_pretty(&bbox_annotations).unwrap_or_else(|_| "[]".into())
    } else {
        String::new()
    };

    let envelope = json!({
        "provider": "mistral",
        "service": "document_ai",
        "operation": "annotations",
        "path": rel_path(root, &resolved),
        "file": {
            "media_type": media_type,
            "size_bytes": size_bytes,
            "source_type": source_type,
        },
        "model": chosen_model,
        "options": {
            "include_images": include_images.unwrap_or(false),
            "pages": normalized_pages,
            "has_document_schema": document_schema.is_some(),
            "has_bbox_schema": bbox_schema.is_some(),
            "instruction": instruction,
        },
        "text": text,
        "document_annotation": document_annotation,
        "bbox_annotations": bbox_annotations,
        "response": parsed,
    });
    ToolResult::ok(serialize_document_envelope(envelope, max_chars))
}

#[allow(clippy::too_many_arguments)]
pub async fn document_qa(
    root: &Path,
    shared_api_key: Option<&str>,
    override_api_key: Option<&str>,
    use_shared_key: bool,
    base_url: &str,
    default_model: &str,
    max_bytes: usize,
    path: &str,
    question: &str,
    model: Option<&str>,
    max_chars: usize,
    request_timeout_sec: u64,
    files_read: &mut HashSet<PathBuf>,
) -> ToolResult {
    let resolved = match filesystem::resolve_path(root, path) {
        Ok(value) => value,
        Err(error) => return ToolResult::error(error),
    };
    if !resolved.exists() {
        return ToolResult::error(format!("File not found: {path}"));
    }
    if resolved.is_dir() {
        return ToolResult::error(format!("Path is a directory, not a file: {path}"));
    }
    let ext = resolved
        .extension()
        .and_then(|value| value.to_str())
        .map(|value| format!(".{}", value.to_ascii_lowercase()))
        .unwrap_or_default();
    if !is_pdf_extension(&ext) {
        return ToolResult::error("document_qa supports only local PDF files in v1".into());
    }
    let api_key = match effective_document_ai_key(shared_api_key, override_api_key, use_shared_key)
    {
        Ok(value) => value,
        Err(error) => return ToolResult::error(error),
    };
    let chosen_model = model.unwrap_or(default_model).trim();
    if chosen_model.is_empty() {
        return ToolResult::error("No Mistral Document AI Q&A model configured".into());
    }
    if question.trim().is_empty() {
        return ToolResult::error("document_qa requires question".into());
    }
    let (data_url, _, media_type, size_bytes) = match build_data_url(&resolved, max_bytes) {
        Ok(value) => value,
        Err(error) => return ToolResult::error(error),
    };
    files_read.insert(resolved.clone());

    let body = json!({
        "model": chosen_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    {"type": "document_url", "document_url": data_url}
                ]
            }
        ]
    });
    let parsed = match request_json(
        api_key,
        &chat_endpoint(base_url),
        &body,
        request_timeout_sec,
        "Mistral Document AI Q&A",
    )
    .await
    {
        Ok(value) => value,
        Err(error) => return ToolResult::error(error),
    };

    let envelope = json!({
        "provider": "mistral",
        "service": "document_ai",
        "operation": "qa",
        "path": rel_path(root, &resolved),
        "file": {
            "media_type": media_type,
            "size_bytes": size_bytes,
            "source_type": "document_url",
        },
        "model": chosen_model,
        "options": {},
        "question": question,
        "text": extract_chat_text(&parsed),
        "response": parsed,
    });
    ToolResult::ok(serialize_document_envelope(envelope, max_chars))
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{body::Bytes, routing::post, Json, Router};
    use tempfile::tempdir;
    use tokio::net::TcpListener;

    async fn capture_ocr(body: Bytes) -> Json<Value> {
        Json(json!({
            "model": "mistral-ocr-latest",
            "pages": [{
                "index": 0,
                "markdown": "# Title\nHello world",
                "images": [{
                    "id": "img-1",
                    "image_base64": "abc123"
                }]
            }],
            "usage_info": {"pages_processed": 1},
            "raw_body": String::from_utf8_lossy(&body).to_string(),
        }))
    }

    async fn capture_annotations(_body: Bytes) -> Json<Value> {
        Json(json!({
            "model": "mistral-ocr-latest",
            "document_annotation": "{\"invoice_number\":\"INV-42\"}",
            "pages": [{"index": 0, "images": []}],
        }))
    }

    async fn capture_qa(_body: Bytes) -> Json<Value> {
        Json(json!({
            "choices": [{
                "message": {
                    "content": "The total is 42 dollars."
                }
            }]
        }))
    }

    async fn spawn_server(route: &str) -> String {
        let app = match route {
            "ocr" => Router::new().route("/v1/ocr", post(capture_ocr)),
            "annotations" => Router::new().route("/v1/ocr", post(capture_annotations)),
            "qa" => Router::new().route("/v1/chat/completions", post(capture_qa)),
            _ => Router::new(),
        };
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });
        format!("http://{}", addr)
    }

    #[test]
    fn test_serialize_document_envelope_omits_large_annotation_fields() {
        let payload = json!({
            "provider": "mistral",
            "service": "document_ai",
            "operation": "annotations",
            "path": "sample.pdf",
            "text": "z".repeat(4_000),
            "document_annotation": {
                "invoice_number": "INV-42",
                "notes": "x".repeat(4_000),
            },
            "bbox_annotations": [{
                "page_index": 0,
                "bbox_annotation": {
                    "label": "stamp",
                    "details": "y".repeat(3_000),
                }
            }],
            "response": {
                "document_annotation": "{\"invoice_number\":\"INV-42\",\"notes\":\"".to_string()
                    + &"x".repeat(4_000)
                    + "\"}",
                "pages": [{
                    "index": 0,
                    "images": [{
                        "image_base64": "b".repeat(2_000),
                        "bbox_annotation": {
                            "label": "stamp",
                            "details": "y".repeat(3_000),
                        }
                    }]
                }]
            }
        });

        let serialized = serialize_document_envelope(payload, 900);

        assert!(
            serialized.len() <= 900,
            "serialized envelope exceeded max_chars"
        );
        let parsed: Value = serde_json::from_str(&serialized).unwrap();
        assert_eq!(parsed["truncation"]["applied"], Value::Bool(true));
        assert!(parsed.get("bbox_annotations").is_none());
        assert!(parsed.get("document_annotation").is_none());
        if let Some(response) = parsed.get("response") {
            assert!(response.get("document_annotation").is_none());
        }
    }

    #[tokio::test]
    async fn test_document_ocr_success() {
        let dir = tempdir().unwrap();
        let pdf = dir.path().join("sample.pdf");
        std::fs::write(&pdf, b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n").unwrap();
        let mut files_read = HashSet::new();
        let result = document_ocr(
            dir.path(),
            Some("mistral-key"),
            None,
            true,
            &spawn_server("ocr").await,
            "mistral-ocr-latest",
            1024 * 1024,
            "sample.pdf",
            Some(true),
            Some(&[0, 2]),
            None,
            20_000,
            5,
            &mut files_read,
        )
        .await;

        assert!(!result.is_error, "unexpected error: {}", result.content);
        let parsed: Value = serde_json::from_str(&result.content).unwrap();
        assert_eq!(parsed["operation"], "ocr");
        assert_eq!(parsed["path"], "sample.pdf");
        assert_eq!(parsed["options"]["pages"], json!([0, 2]));
        assert_eq!(
            parsed["artifacts"]["markdown_path"],
            json!("sample.pdf.ocr.pages-1_3.md")
        );
        assert_eq!(
            parsed["artifacts"]["json_path"],
            json!("sample.pdf.ocr.pages-1_3.json")
        );
        let markdown_artifact = dir.path().join("sample.pdf.ocr.pages-1_3.md");
        let json_artifact = dir.path().join("sample.pdf.ocr.pages-1_3.json");
        assert!(markdown_artifact.exists());
        assert!(json_artifact.exists());
        let markdown = std::fs::read_to_string(&markdown_artifact).unwrap();
        assert!(markdown.contains("# Title\nHello world"));
        let saved_payload: Value =
            serde_json::from_str(&std::fs::read_to_string(&json_artifact).unwrap()).unwrap();
        assert_eq!(saved_payload["text"], json!("# Title\nHello world"));
        assert!(
            saved_payload["response"]["pages"][0]["images"][0]
                .get("image_base64")
                .is_none()
        );
        assert!(parsed["response"]["raw_body"]
            .as_str()
            .unwrap()
            .contains("\"document_url\":\"data:application/pdf;base64,"));
    }

    #[tokio::test]
    async fn test_document_annotations_requires_schema() {
        let dir = tempdir().unwrap();
        let pdf = dir.path().join("sample.pdf");
        std::fs::write(&pdf, b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n").unwrap();
        let mut files_read = HashSet::new();
        let result = document_annotations(
            dir.path(),
            Some("mistral-key"),
            None,
            true,
            "https://api.mistral.ai",
            "mistral-ocr-latest",
            1024 * 1024,
            "sample.pdf",
            None,
            None,
            None,
            None,
            None,
            None,
            20_000,
            5,
            &mut files_read,
        )
        .await;
        assert!(result.is_error);
        assert!(result.content.contains("requires document_schema"));
    }

    #[tokio::test]
    async fn test_document_annotations_success() {
        let dir = tempdir().unwrap();
        let pdf = dir.path().join("sample.pdf");
        std::fs::write(&pdf, b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n").unwrap();
        let mut files_read = HashSet::new();
        let result = document_annotations(
            dir.path(),
            Some("mistral-key"),
            None,
            true,
            &spawn_server("annotations").await,
            "mistral-ocr-latest",
            1024 * 1024,
            "sample.pdf",
            Some(&json!({
                "type": "object",
                "properties": {"invoice_number": {"type": "string"}},
                "required": ["invoice_number"]
            })),
            None,
            Some("Extract the invoice number."),
            None,
            None,
            None,
            20_000,
            5,
            &mut files_read,
        )
        .await;
        assert!(!result.is_error, "unexpected error: {}", result.content);
        let parsed: Value = serde_json::from_str(&result.content).unwrap();
        assert_eq!(parsed["operation"], "annotations");
        assert_eq!(parsed["document_annotation"]["invoice_number"], "INV-42");
    }

    #[tokio::test]
    async fn test_document_qa_rejects_non_pdf() {
        let dir = tempdir().unwrap();
        let image = dir.path().join("receipt.png");
        std::fs::write(&image, b"\x89PNG\r\n\x1a\n").unwrap();
        let mut files_read = HashSet::new();
        let result = document_qa(
            dir.path(),
            Some("mistral-key"),
            None,
            true,
            "https://api.mistral.ai",
            "mistral-small-latest",
            1024 * 1024,
            "receipt.png",
            "What is the total?",
            None,
            20_000,
            5,
            &mut files_read,
        )
        .await;
        assert!(result.is_error);
        assert!(result.content.contains("supports only local PDF files"));
    }

    #[tokio::test]
    async fn test_document_qa_override_key_mode() {
        let dir = tempdir().unwrap();
        let pdf = dir.path().join("sample.pdf");
        std::fs::write(&pdf, b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n").unwrap();
        let mut files_read = HashSet::new();
        let result = document_qa(
            dir.path(),
            None,
            Some("docai-key"),
            false,
            &spawn_server("qa").await,
            "mistral-small-latest",
            1024 * 1024,
            "sample.pdf",
            "What is the total?",
            None,
            20_000,
            5,
            &mut files_read,
        )
        .await;
        assert!(!result.is_error, "unexpected error: {}", result.content);
        let parsed: Value = serde_json::from_str(&result.content).unwrap();
        assert_eq!(parsed["operation"], "qa");
        assert_eq!(parsed["text"], "The total is 42 dollars.");
    }
}
