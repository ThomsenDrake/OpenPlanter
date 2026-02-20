# OpenPlanter demo recording — captures the TUI through the agent's
# working phase (thinking spinner, tool calls) but stops before the
# final answer renders.
#
# Usage:
#   brew install charmbracelet/tap/vhs
#   vhs demo.tape -o demo.gif
#
# Adjust Sleep durations after a dry run to match actual agent timing.

Set Shell "bash"
Set FontSize 15
Set Width 1400
Set Height 800
Set Theme "Catppuccin Mocha"
Set TypingSpeed 65ms
Set Padding 20

# Boot the TUI in demo mode
Type "python -m agent --demo"
Enter
Sleep 4s

# Let the splash art and startup info settle
Sleep 1s

# Type the prompt with a human-like cadence
Type "Investigate local politicians for evidence of corruption."
Sleep 800ms
Enter

# Agent is now working — capture the thinking spinner and tool call tree.
# The first model call usually starts within 1-2s; tool calls stream after.
# Adjust this duration based on a dry run. 45s typically covers several
# steps of thinking + tool execution without reaching the final answer.
Sleep 45s
