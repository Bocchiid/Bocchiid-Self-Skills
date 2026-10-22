<#
word_com.ps1 - drive Microsoft Word through COM for the three things
python-docx cannot do: open legacy .doc, refresh fields, export PDF.

    powershell -File word_com.ps1 -Action to-docx -In  template.doc  -Out work.docx
    powershell -File word_com.ps1 -Action to-doc  -In  out.docx     -Out report.doc
    powershell -File word_com.ps1 -Action to-pdf  -In  out.docx     -Out preview.pdf

to-doc / to-pdf refresh every field (SEQ / REF / TOC) twice and force a
repaginate before saving, so the cached field results in the file are correct
even for readers who never press F9.

NOTE: keep this file pure ASCII. Windows PowerShell 5.1 parses a .ps1 as ANSI
unless it has a BOM, so Chinese characters *inside the script* turn into
mojibake; Chinese paths passed as -In/-Out arguments are fine.
#>
param(
  [Parameter(Mandatory = $true)][ValidateSet('to-docx', 'to-doc', 'to-pdf', 'fields', 'compat', 'audit', 'roundtrip')]
  [string]$Action,
  [Parameter(Mandatory = $true)][string]$In,
  [string]$Out
)

$ErrorActionPreference = 'Stop'

# Word COM resolves relative paths against .NET's CurrentDirectory, and
# `powershell -File` does NOT sync $PWD into it (it stays at system32).
# Without this, any relative -In/-Out silently looks in the wrong place.
[System.Environment]::CurrentDirectory = (Get-Location).Path
if (-not [System.IO.Path]::IsPathRooted($In)) {
  $In = Join-Path (Get-Location).Path $In
}
if ($Out -and -not [System.IO.Path]::IsPathRooted($Out)) {
  $Out = Join-Path (Get-Location).Path $Out
}

if (-not (Test-Path -LiteralPath $In)) {
  Write-Error "input not found: $In"
  exit 2
}

function Test-Locked([string]$path) {
  if (-not $path -or -not (Test-Path -LiteralPath $path)) { return $false }
  try {
    $fs = [System.IO.File]::Open($path, 'Open', 'ReadWrite', 'None')
    $fs.Close()
    return $false
  } catch {
    return $true
  }
}

# A file open in Word/WPS is locked; retrying the same overwrite only wastes time.
# Fail fast with exit code 3 so the caller can write a "-revised" copy instead.
$writeTargets = @()
if ($Action -in @('fields', 'compat', 'roundtrip')) { $writeTargets += $In }
if ($Out -and $Action -in @('to-docx', 'to-doc', 'to-pdf', 'roundtrip')) {
  $writeTargets += $Out
}
if (-not $Out -and $Action -in @('to-docx', 'to-doc', 'to-pdf')) {
  $writeTargets += $In
}
foreach ($target in $writeTargets) {
  if (Test-Locked $target) {
    Write-Host "FILE_LOCKED: $target" -ForegroundColor Red
    Write-Host "Close Word/WPS (or remove the ~`$ lock file), then retry." -ForegroundColor Yellow
    Write-Host "Meanwhile write to a new name such as '-revised' and tell the user which file is final."
    exit 3
  }
}

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0

try {
  # Read-only for pure reads; the others must be able to save.
  $readOnly = ($Action -in @('to-docx', 'to-pdf', 'audit'))
  # Word occasionally refuses to open a file that plainly exists (an instance
  # from a previous run still shutting down, a slow network path). Retrying here
  # is cheaper than making every caller handle it.
  # NOTE: before blaming this, echo the path you passed - `"dir\$f.docx"` in bash
  # silently becomes `dir$f.docx` and lands here too. See references/docx-cookbook.md.
  $doc = $null
  for ($attempt = 1; $attempt -le 3; $attempt++) {
    try { $doc = $word.Documents.Open($In, $false, $readOnly); break }
    catch {
      if ($attempt -eq 3) { throw }
      Write-Host ("open failed, retrying ($attempt/3) ...") -ForegroundColor Yellow
      Start-Sleep -Milliseconds 900
    }
  }
  $target = if ($Out) { $Out } else { $In }

  $metrics = {
    param($d)
    $omml = -1
    try { $omml = $d.OMaths.Count } catch { }
    $inline = $d.InlineShapes.Count
    [pscustomobject]@{
      compatibility_mode = $d.CompatibilityMode
      omml = $omml
      inline_shapes = $inline
      tables = $d.Tables.Count
      pages = $d.ComputeStatistics(2)
    }
  }

  switch ($Action) {
    'to-docx' {
      $doc.SaveAs2($target, 16)                                 # wdFormatXMLDocument
      # 11 means Word 2003. Keeping it makes Word turn OMML formulas into
      # pictures on save and warn about "older version" on close.
      # Set it *after* SaveAs2: a read-only source may reject the change.
      # CompatibilityMode is read-only; use the SetCompatibilityMode method.
      try { $doc.SetCompatibilityMode(15); $doc.Save() } catch { }
    }
    'to-doc' {
      try { $doc.Fields.Update() | Out-Null } catch { }
      try { $doc.Fields.Update() | Out-Null } catch { }
      $doc.Repaginate()
      $m = & $metrics $doc
      if ($m.omml -gt 0) {
        Write-Host ("WARNING: " + $m.omml + " OMML formulas; .doc converts them to pictures.") -ForegroundColor Yellow
      }
      Write-Host ("pages: " + $m.pages)
      $doc.SaveAs2($target, 0)                                  # wdFormatDocument
    }
    'to-pdf' {
      try { $doc.Fields.Update() | Out-Null } catch { }
      try { $doc.Fields.Update() | Out-Null } catch { }
      $doc.Repaginate()
      Write-Host ("pages: " + $doc.ComputeStatistics(2))
      $doc.SaveAs2($target, 17)                                 # wdFormatPDF
    }
    'fields' {
      try { $doc.Fields.Update() | Out-Null } catch { }
      try { $doc.Fields.Update() | Out-Null } catch { }
      $doc.Repaginate()
      $doc.Save()
    }
    'compat' {
      $doc.SetCompatibilityMode(15)
      $doc.Save()
      Write-Host ("compatibility_mode: " + $doc.CompatibilityMode)
    }
    'audit' {
      $m = & $metrics $doc
      $m | ConvertTo-Json -Compress
    }
    'roundtrip' {
      # Open -> save -> close -> reopen. OMML / InlineShapes must not change.
      $before = & $metrics $doc
      $doc.Save()
      $doc.Close($false)
      $doc = $word.Documents.Open($In, $false, $false)
      $after = & $metrics $doc
      $changed = (($before.omml -ne $after.omml) -or
                  ($before.inline_shapes -ne $after.inline_shapes))
      [pscustomobject]@{
        before = $before
        after = $after
        ok = (-not $changed)
        warning = $(if ($changed) { "OMML/InlineShapes changed after save; formulas may have become pictures." } else { "" })
      } | ConvertTo-Json -Compress -Depth 4
      if ($changed) { exit 4 }
    }
  }
  if ($doc -ne $null) { $doc.Close($false) }
  Write-Host "ok: $Action -> $target"
} catch {
  Write-Host ("FAILED: " + $_.Exception.Message) -ForegroundColor Red
  Write-Host "A 'file is corrupt' message here almost always means the OOXML is invalid."
  Write-Host "Most common causes: a w:tc ending with a w:tbl, or child elements out of"
  Write-Host "schema order inside w:pPr / w:rPr / w:tblPr. See references/docx-cookbook.md."
  exit 1
} finally {
  $word.Quit()
  [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}
