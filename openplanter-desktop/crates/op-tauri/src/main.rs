// Prevents additional console window on Windows in release.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod bridge;
mod commands;
mod state;

use state::AppState;

fn main() {
    let state = match AppState::try_new() {
        Ok(state) => state,
        Err(err) => {
            eprintln!("[startup:error] {err}");
            std::process::exit(2);
        }
    };
    eprintln!("[startup:info] {}", state.startup_trace());

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(state)
        .invoke_handler(tauri::generate_handler![
            commands::agent::solve,
            commands::agent::cancel,
            commands::agent::debug_log,
            commands::config::get_config,
            commands::config::update_config,
            commands::config::list_models,
            commands::config::save_settings,
            commands::config::save_credential,
            commands::config::get_credentials_status,
            commands::init::get_init_status,
            commands::init::run_standard_init,
            commands::init::complete_first_run_gate,
            commands::init::inspect_migration_source,
            commands::init::run_migration_init,
            commands::session::list_sessions,
            commands::session::open_session,
            commands::session::delete_session,
            commands::session::get_session_history,
            commands::session::get_session_directory,
            commands::session::write_session_artifact,
            commands::session::read_session_artifact,
            commands::session::read_session_event,
            commands::handoff::export_session_handoff,
            commands::handoff::import_session_handoff,
            commands::wiki::get_graph_data,
            commands::wiki::get_investigation_overview,
            commands::wiki::read_wiki_file,
        ])
        .run(tauri::generate_context!("tauri.conf.json"))
        .expect("error while running tauri application");
}
