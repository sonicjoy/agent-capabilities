<#
.SYNOPSIS
  Set up Claude Code to use the same skills, rules, knowledge and MCP servers as Cursor.

.DESCRIPTION
  Safe to re-run. Nothing is deleted. Steps:
    1. Link each skill in <agent-capabilities>/skills into ~/.claude/skills and ~/.cursor/skills (directory
       junctions, no admin needed).
    2. Add a managed block to ~/.claude/CLAUDE.md that imports claude/CLAUDE.md from this repo,
       plus your personal Cursor user rules from ~/.cursor/rules that are not in this repo. Add a SessionStart hook
       to ~/.claude/settings.json that loads the working agreement live from the KB graph
       (claude/hooks/kb_session_context.py).
    3. Copy MCP servers from ~/.cursor/mcp.json into Claude Code (user scope) with `claude mcp add`.
       Servers that already exist in Claude Code are skipped. Cursor's ${env:NAME} references become ${NAME}.
       Warns about Neo4j servers that use the admin login, or KB servers without --read-only.
    4. For each repo under -ReposRoot that has .cursor/rules or AGENTS.md and no CLAUDE.md, write a
       CLAUDE.md that loads them, and hide it from git with .git/info/exclude.
    5. Load the mods in claude/mods (the agent-watch pane) in every session: CLAUDE_CODE_PLUGIN_DIRS in
       ~/.claude/settings.json points at their folders here, watched, so a git pull reaches running sessions.

  Run with -DryRun first to see what it would do.

.EXAMPLE
  cd C:\repos\agent-capabilities
  .\scripts\setup-claude-code.ps1 -DryRun
  .\scripts\setup-claude-code.ps1
#>
[CmdletBinding()]
param(
  [string]$ReposRoot = "C:\repos",
  [string]$CursorMcpJson = (Join-Path $HOME ".cursor\mcp.json"),
  [switch]$DryRun,
  [switch]$SkipSkills,
  [switch]$SkipClaudeMd,
  [switch]$SkipMcp,
  [switch]$SkipRepos,
  [switch]$SkipMods
)

$ErrorActionPreference = "Stop"
$AgentCaps = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ClaudeHome = Join-Path $HOME ".claude"

function Say($msg, $color = "Gray") { Write-Host $msg -ForegroundColor $color }
function Act($msg) { if ($DryRun) { Say "  [dry-run] $msg" "Yellow" } else { Say "  $msg" "Green" } }
function ToFwd($p) { return ($p -replace '\\', '/') }

# Run a native command without Windows PowerShell 5.1 turning its stderr into a terminating error
function Invoke-Native([string]$exe, [string[]]$argv) {
  $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
  try { $out = & $exe @argv 2>$null; return ,@($out) } finally { $ErrorActionPreference = $old }
}

# Warn about a Neo4j MCP server that could write the Colossus KB behind kb.py's back: the shared admin login
# (also through a ${env:NAME} / ${NAME} reference), or a KB server without --read-only. Never prints values.
function Test-Neo4jServer([string]$where, [string]$name, $s) {
  if (-not (@($s.args) -match 'mcp-neo4j-cypher')) { return }
  $user = if ($s.env) { "$($s.env.NEO4J_USERNAME)" } else { "" }
  if ($user -match '^\$\{(?:env:)?(\w+)\}$') { $user = [Environment]::GetEnvironmentVariable($Matches[1], "User") }
  if ($user -eq 'neo4j') {
    Say "  WARN  $where server '$name' uses the Neo4j admin login 'neo4j': agents could write the KB through it. Fine for other work; for the KB use neo4j-colossus-kb (scripts/setup_kb.py, mcp/README.md)."  "Red"
  }
  if ($name -match 'kb' -and -not (@($s.args) -contains '--read-only')) {
    Say "  WARN  $where server '$name' looks like a KB server but isn't --read-only (mcp/README.md)." "Red"
  }
}

# Write UTF-8 without BOM on Windows PowerShell 5.1 and PowerShell 7
function Write-Utf8($path, $text) {
  $enc = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($path, $text, $enc)
}

Say "agent-capabilities: $AgentCaps" "Cyan"
if (-not $DryRun -and -not (Test-Path $ClaudeHome)) { New-Item -ItemType Directory -Path $ClaudeHome | Out-Null }

# ---------------------------------------------------------------- 1. skills
if (-not $SkipSkills) {
  # Both tools load skills from their own folder; the same junctions serve both.
  foreach ($skillsDir in @((Join-Path $ClaudeHome "skills"), (Join-Path $HOME ".cursor\skills"))) {
    Say "`n[1/5] Skills -> $skillsDir" "Cyan"
    if (-not $DryRun -and -not (Test-Path $skillsDir)) { New-Item -ItemType Directory -Path $skillsDir | Out-Null }
    Get-ChildItem (Join-Path $AgentCaps "skills") -Directory | Where-Object { Test-Path (Join-Path $_.FullName "SKILL.md") } | ForEach-Object {
      $link = Join-Path $skillsDir $_.Name
      if (Test-Path $link) {
        $item = Get-Item $link -Force
        if ($item.LinkType -and ($item.Target -contains $_.FullName -or "$($item.Target)" -eq $_.FullName)) { Say "  ok    $($_.Name) (already linked)" }
        else { Say "  skip  $($_.Name): $link already exists and is not a link to this repo" "DarkYellow" }
      } else {
        Act "link  $($_.Name) -> $($_.FullName)"
        if (-not $DryRun) { New-Item -ItemType Junction -Path $link -Target $_.FullName | Out-Null }
      }
    }
  }
}

# ---------------------------------------------------------------- 2. user CLAUDE.md
if (-not $SkipClaudeMd) {
  Say "`n[2/5] $ClaudeHome\CLAUDE.md" "Cyan"
  $begin = "<!-- BEGIN agent-capabilities (managed by setup-claude-code.ps1) -->"
  $end   = "<!-- END agent-capabilities -->"
  $lines = @($begin, "@$(ToFwd (Join-Path $AgentCaps 'claude\CLAUDE.md'))")

  # Personal Cursor user rules not already shared through this repo
  $sharedRules = @(Get-ChildItem (Join-Path $AgentCaps "rules") -Filter *.mdc -ErrorAction SilentlyContinue | ForEach-Object { $_.Name })
  $userRules = Join-Path $HOME ".cursor\rules"
  if (Test-Path $userRules) {
    $personal = @(Get-ChildItem $userRules -Filter *.mdc | Where-Object { $sharedRules -notcontains $_.Name })
    if ($personal.Count -gt 0) {
      $lines += ""
      $lines += "Personal rules shared with Cursor (~/.cursor/rules):"
      foreach ($r in $personal) { $lines += "@~/.cursor/rules/$($r.Name)" }
    }
  }
  if (Test-Path (Join-Path $HOME ".cursor\knowledge\index.md")) {
    $lines += ""
    $lines += "Personal knowledge base (other companies, e.g. White Swan Data): ~/.cursor/knowledge/index.md. Read it when working on those repos."
  }
  $lines += $end
  $block = ($lines -join "`r`n")

  $userMd = Join-Path $ClaudeHome "CLAUDE.md"
  $existing = if (Test-Path $userMd) { [System.IO.File]::ReadAllText($userMd) } else { "" }
  $pattern = [regex]::Escape($begin) + "[\s\S]*?" + [regex]::Escape($end)
  if ($existing -match $pattern) { $new = [regex]::Replace($existing, $pattern, { param($m) $block }) }
  elseif ($existing.Trim()) { $new = $existing.TrimEnd() + "`r`n`r`n" + $block + "`r`n" }
  else { $new = $block + "`r`n" }
  Act "write managed block ($($lines.Count - 2) lines) to $userMd"
  if ($DryRun) { $block -split "`r`n" | ForEach-Object { Say "      $_" "DarkGray" } }
  else { Write-Utf8 $userMd $new }

  # SessionStart hook: the working agreement is read live from the KB graph, not from the markdown export (#19).
  # Our entry is found by its script name and replaced; every other setting and hook is kept.
  $settingsPath = Join-Path $ClaudeHome "settings.json"
  $hookScript = ToFwd (Join-Path $AgentCaps "claude\hooks\kb_session_context.py")
  $hookCommand = "python `"$hookScript`""
  $settings = if (Test-Path $settingsPath) { [System.IO.File]::ReadAllText($settingsPath) | ConvertFrom-Json } else { New-Object PSObject }
  if (-not $settings.hooks) { $settings | Add-Member -NotePropertyName hooks -NotePropertyValue (New-Object PSObject) -Force }
  $kept = @(@($settings.hooks.SessionStart) | Where-Object { $_ -and -not (@($_.hooks) | Where-Object { "$($_.command)" -match 'kb_session_context\.py' }) })
  $ours = [PSCustomObject]@{ hooks = @([PSCustomObject]@{ type = "command"; command = $hookCommand; timeout = 30 }) }
  $settings.hooks | Add-Member -NotePropertyName SessionStart -NotePropertyValue (@($kept) + $ours) -Force
  Act "SessionStart hook in $settingsPath -> $hookCommand"
  if (-not $DryRun) { Write-Utf8 $settingsPath ($settings | ConvertTo-Json -Depth 20) }
}

# ---------------------------------------------------------------- 3. MCP servers
if (-not $SkipMcp) {
  Say "`n[3/5] MCP servers from $CursorMcpJson" "Cyan"
  if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Say "  'claude' is not on PATH. Install Claude Code, open a new terminal, then re-run with -SkipSkills -SkipClaudeMd -SkipRepos." "Red"
  } elseif (-not (Test-Path $CursorMcpJson)) {
    Say "  $CursorMcpJson not found, skipping." "DarkYellow"
  } else {
    $cfg = Get-Content $CursorMcpJson -Raw | ConvertFrom-Json
    $existingNames = @()
    Say "  reading existing Claude Code servers (claude mcp list checks each one, can take a minute)..."
    $listOut = (Invoke-Native "claude" @("mcp", "list")) -join "`n"
    foreach ($srv in $cfg.mcpServers.PSObject.Properties) {
      $orig = $srv.Name
      $s = $srv.Value
      # Claude Code server names: letters, digits, - and _
      $name = ($orig.ToLower() -replace '[^a-z0-9_-]+', '-').Trim('-')
      if ($s.disabled -eq $true) { Say "  skip  $orig (disabled in Cursor)"; continue }
      Test-Neo4jServer "Cursor" $orig $s
      if ($listOut -match "(?m)^$([regex]::Escape($name)):") { Say "  ok    $name (already in Claude Code)"; continue }

      # Name goes straight after "add": --env takes several values and would swallow a later name
      $cmdArgs = @("mcp", "add", $name, "--scope", "user")
      $shown = @()
      if ($s.url) {
        $cmdArgs += @("--transport", "http", $s.url)
        $shown = $cmdArgs
      } elseif ($s.command) {
        $cmdArgs += @("--transport", "stdio")
        $shown = $cmdArgs.Clone()
        if ($s.env) {
          foreach ($e in $s.env.PSObject.Properties) {
            # Cursor's ${env:NAME} is ${NAME} in Claude Code: both read the user environment, nothing is stored
            $value = "$($e.Value)" -replace '\$\{env:(\w+)\}', '$${$1}'
            $cmdArgs += @("--env", "$($e.Name)=$value")
            $val = if ($e.Name -match 'PASS|SECRET|TOKEN|KEY' -and $value -notmatch '^\$\{\w+\}$') { "***" } else { $value }
            $shown += @("--env", "$($e.Name)=$val")
          }
        }
        # Cursor's Redshift entry uses a Windows-only uv.exe path; uvx works everywhere
        $command = $s.command; $argList = @($s.args)
        if ($command -match 'uv(\.exe)?$' -and $argList.Count -ge 4 -and $argList[0] -eq 'tool' -and $argList[1] -eq 'run' -and $argList[2] -eq '--from') {
          $command = "uvx"; $argList = @($argList[3])
        }
        $tail = @("--", $command) + $argList
        $cmdArgs += $tail; $shown += $tail
      } else { Say "  skip  $orig (no url or command)" "DarkYellow"; continue }

      Act ("claude " + (($shown | ForEach-Object { if ($_ -match '\s') { "`"$_`"" } else { $_ } }) -join ' '))
      if (-not $DryRun) {
        Invoke-Native "claude" $cmdArgs | Out-Null
        if ($LASTEXITCODE -ne 0) { Say "  FAILED to add $name (exit $LASTEXITCODE)" "Red" }
      }
    }
    Say "  Note: like Cursor's mcp.json, Claude Code stores these values (including passwords) in ~/.claude.json." "DarkGray"
  }
  # Servers added to Claude Code directly never pass through the loop above
  $claudeJson = Join-Path $HOME ".claude.json"
  if (Test-Path $claudeJson) {
    $cc = Get-Content $claudeJson -Raw | ConvertFrom-Json
    if ($cc.mcpServers) { foreach ($srv in $cc.mcpServers.PSObject.Properties) { Test-Neo4jServer "Claude Code" $srv.Name $srv.Value } }
  }
}

# ---------------------------------------------------------------- 4. per-repo CLAUDE.md
if (-not $SkipRepos) {
  Say "`n[4/5] Repo CLAUDE.md files under $ReposRoot" "Cyan"
  $marker = "Generated by agent-capabilities/scripts/setup-claude-code.ps1"
  $utf8 = New-Object System.Text.UTF8Encoding($false)
  Get-ChildItem $ReposRoot -Directory | ForEach-Object {
    $repo = $_.FullName
    if (-not (Test-Path (Join-Path $repo ".git"))) { return }
    if ($repo -eq $AgentCaps) { return }
    $rulesDir = Join-Path $repo ".cursor\rules"
    $rules = @()
    if (Test-Path $rulesDir) { $rules = @(Get-ChildItem $rulesDir -Recurse -File -Include *.mdc, *.md | Sort-Object FullName) }
    $agentsMd = Test-Path (Join-Path $repo "AGENTS.md")
    if ($rules.Count -eq 0 -and -not $agentsMd) { return }

    # Our own generated CLAUDE.md is refreshed. A CLAUDE.md the team wrote is left alone and the
    # generated content goes to CLAUDE.local.md instead (also loaded by Claude Code, never committed).
    $target = "CLAUDE.md"
    $claudeMd = Join-Path $repo "CLAUDE.md"
    if ((Test-Path $claudeMd) -and -not ([System.IO.File]::ReadAllText($claudeMd, $utf8).Contains($marker))) { $target = "CLAUDE.local.md" }
    $targetPath = Join-Path $repo $target

    $out = @("# $($_.Name)", "", "$marker from this repo's Cursor rules. Cursor and Claude Code share these instructions; edit the sources, not this file.", "")
    if ($agentsMd) { $out += "@AGENTS.md"; $out += "" }
    $always = @(); $scoped = @()
    foreach ($r in $rules) {
      $rel = ToFwd ($r.FullName.Substring($repo.Length + 1))
      # Read as UTF-8: Windows PowerShell 5.1 Get-Content would read it as ANSI and garble dashes
      $head = (@([System.IO.File]::ReadAllLines($r.FullName, $utf8)) | Select-Object -First 15) -join "`n"
      $desc = if ($head -match '(?m)^description:\s*(.+)$') { $Matches[1].Trim('"', "'", ' ') } else { "" }
      $globs = if ($head -match '(?m)^globs:\s*(.+)$') { $Matches[1].Trim('"', "'", ' ') } else { "" }
      if ($head -match '(?m)^alwaysApply:\s*true') { $always += "@$rel" }
      else {
        $when = if ($globs) { "when editing ``$globs``" } else { "when relevant" }
        $scoped += "- ``$rel``: $desc (read $when)"
      }
    }
    if ($always.Count) { $out += "## Always-on rules"; $out += ""; $out += $always; $out += "" }
    if ($scoped.Count) { $out += "## Rules to read when they apply"; $out += ""; $out += $scoped; $out += "" }
    $text = ($out -join "`r`n") + "`r`n"

    $current = if (Test-Path $targetPath) { [System.IO.File]::ReadAllText($targetPath, $utf8) } else { $null }
    if ($current -eq $text) { Say "  ok    $($_.Name)\$target (up to date)"; return }
    Act "write $($_.Name)\$target ($($always.Count) always-on, $($scoped.Count) scoped$(if ($agentsMd) { ', AGENTS.md' }))"
    if (-not $DryRun) {
      Write-Utf8 $targetPath $text
      # Keep it out of git status: write to the repo's (or main worktree's) info/exclude
      $common = (Invoke-Native "git" @("-C", $repo, "rev-parse", "--git-common-dir")) | Select-Object -First 1
      if ($LASTEXITCODE -eq 0 -and $common) {
        if (-not [System.IO.Path]::IsPathRooted($common)) { $common = Join-Path $repo $common }
        $exclude = Join-Path $common "info\exclude"
        if (-not (Test-Path (Split-Path $exclude))) { New-Item -ItemType Directory -Path (Split-Path $exclude) | Out-Null }
        $cur = if (Test-Path $exclude) { Get-Content $exclude } else { @() }
        if ($cur -notcontains "/$target") { Add-Content -Path $exclude -Value "/$target" }
      }
    }
  }
}

# ---------------------------------------------------------------- 5. mods
if (-not $SkipMods) {
  Say "`n[5/5] Claude Code mods -> CLAUDE_CODE_PLUGIN_DIRS in $ClaudeHome\settings.json" "Cyan"
  # Loaded straight from this repo's folder and watched, so a git pull reaches running sessions; a
  # marketplace install would run a frozen copy. Another agent-watch folder in the list is replaced,
  # any other folder is kept.
  $settingsPath = Join-Path $ClaudeHome "settings.json"
  $settings = if (Test-Path $settingsPath) { [System.IO.File]::ReadAllText($settingsPath) | ConvertFrom-Json } else { New-Object PSObject }
  if (-not $settings.env) { $settings | Add-Member -NotePropertyName env -NotePropertyValue (New-Object PSObject) -Force }
  $sep = [System.IO.Path]::PathSeparator
  $mods = @(Get-ChildItem (Join-Path $AgentCaps "claude\mods") -Directory -ErrorAction SilentlyContinue |
    Where-Object { Test-Path (Join-Path $_.FullName ".claude-plugin\plugin.json") } | ForEach-Object { $_.FullName })
  $current = @("$($settings.env.CLAUDE_CODE_PLUGIN_DIRS)" -split [regex]::Escape("$sep") | ForEach-Object { $_.Trim() } | Where-Object { $_ })
  $modNames = @($mods | ForEach-Object { Split-Path $_ -Leaf })
  $others = @($current | Where-Object { $modNames -notcontains (Split-Path $_.TrimEnd('\', '/') -Leaf) })
  $wanted = (@($others) + @($mods)) -join $sep
  if ($mods.Count -eq 0) { Say "  no mods in $(Join-Path $AgentCaps 'claude\mods'), skipping." "DarkYellow" }
  elseif ("$($settings.env.CLAUDE_CODE_PLUGIN_DIRS)" -eq $wanted -and "$($settings.env.CLAUDE_CODE_PLUGIN_DIR_WATCH)" -eq "1") {
    Say "  ok    $($modNames -join ', ') (already loaded from this repo)"
  } else {
    foreach ($m in $mods) { Act "load  $(Split-Path $m -Leaf) from $m" }
    foreach ($o in $others) { Say "  keep  $o" }
    $settings.env | Add-Member -NotePropertyName CLAUDE_CODE_PLUGIN_DIRS -NotePropertyValue $wanted -Force
    $settings.env | Add-Member -NotePropertyName CLAUDE_CODE_PLUGIN_DIR_WATCH -NotePropertyValue "1" -Force
    if (-not $DryRun) { Write-Utf8 $settingsPath ($settings | ConvertTo-Json -Depth 20) }
  }
  Say "  New sessions load them. An 'Agent watch' button sits above the prompt; /agent-watch opens the pane too." "DarkGray"
}

Say "`nDone. Open a new terminal, cd into a repo, run 'claude', then '/memory' to see what it loaded and '/mcp' to check servers." "Cyan"
Say "Cursor doesn't read rule files from ~/.cursor/rules: paste $(Join-Path $AgentCaps 'cursor\user-rules.md') into Cursor Settings > Rules > User Rules (once, and again when it changes)." "Cyan"
