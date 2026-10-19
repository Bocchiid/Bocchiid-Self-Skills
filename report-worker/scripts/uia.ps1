param(
    [Parameter(Mandatory=$true)][ValidateSet("find","click","wait","list","focus")]
    [string]$Action,
    [string]$Window = "",
    [string]$Name = "",
    [string]$AutomationId = "",
    [int]$Timeout = 10
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WorkerMouse {
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint dwData, UIntPtr dwExtraInfo);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
"@

$AE = [System.Windows.Automation.AutomationElement]
$Scope = [System.Windows.Automation.TreeScope]

function Get-WindowElement {
    $root = $AE::RootElement
    if ([string]::IsNullOrWhiteSpace($Window)) { return $root }
    $cond = New-Object System.Windows.Automation.PropertyCondition($AE::NameProperty, $Window)
    $el = $root.FindFirst($Scope::Children, $cond)
    if ($null -ne $el) { return $el }
    $children = $root.FindAll($Scope::Children, [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($child in $children) {
        try {
            if ($child.Current.Name -and $child.Current.Name.ToLower().Contains($Window.ToLower())) {
                return $child
            }
        } catch { }
    }
    return $null
}

function Get-Control {
    param($Parent)
    if ($null -eq $Parent) { return $null }
    $conds = @()
    if (-not [string]::IsNullOrWhiteSpace($Name)) {
        $conds += New-Object System.Windows.Automation.PropertyCondition($AE::NameProperty, $Name)
    }
    if (-not [string]::IsNullOrWhiteSpace($AutomationId)) {
        $conds += New-Object System.Windows.Automation.PropertyCondition($AE::AutomationIdProperty, $AutomationId)
    }
    if ($conds.Count -eq 0) { return $null }
    if ($conds.Count -eq 1) {
        $cond = $conds[0]
    } else {
        $cond = New-Object System.Windows.Automation.AndCondition($conds)
    }
    $el = $Parent.FindFirst($Scope::Descendants, $cond)
    if ($null -ne $el) { return $el }
    # Substring fallback for applications that expose long or decorated names
    # (packet trees, menus, toolbars).
    if (-not [string]::IsNullOrWhiteSpace($Name)) {
        $all = $Parent.FindAll($Scope::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
        foreach ($c in $all) {
            try {
                if ($c.Current.Name -and $c.Current.Name.ToLower().Contains($Name.ToLower())) {
                    return $c
                }
            } catch { }
        }
    }
    return $null
}

function SafeInt($Value) {
    if ($null -eq $Value) { return -1 }
    try {
        $d = [double]$Value
        if ([double]::IsNaN($d) -or [double]::IsInfinity($d)) { return -1 }
        if ($d -gt [int]::MaxValue) { return [int]::MaxValue }
        if ($d -lt [int]::MinValue) { return [int]::MinValue }
        return [int]$d
    } catch {
        return -1
    }
}

function Describe($El) {
    if ($null -eq $El) { return $null }
    $r = $El.Current.BoundingRectangle
    $ct = $El.Current.ControlType.ProgrammaticName -replace "^ControlType\.", ""
    return [ordered]@{
        ok = $true
        name = $El.Current.Name
        automation_id = $El.Current.AutomationId
        control_type = $ct
        enabled = $El.Current.IsEnabled
        offscreen = $El.Current.IsOffscreen
        handle = $El.Current.NativeWindowHandle
        rect = [ordered]@{
            x = SafeInt $r.X
            y = SafeInt $r.Y
            width = SafeInt $r.Width
            height = SafeInt $r.Height
        }
    }
}

function Find-WithWait {
    $parent = Get-WindowElement
    if ($null -eq $parent) {
        return [ordered]@{ ok = $false; error = "window_not_found"; window = $Window }
    }
    $deadline = (Get-Date).AddSeconds([Math]::Max(1, $Timeout))
    do {
        $el = Get-Control $parent
        if ($null -ne $el) { return (Describe $el) }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $deadline)
    return [ordered]@{ ok = $false; error = "control_not_found"; window = $Window; name = $Name; automation_id = $AutomationId }
}

function Click-Control($El) {
    $pattern = $null
    if ($El.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$pattern)) {
        $pattern.Invoke()
        return "Invoke"
    }
    $pattern = $null
    if ($El.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$pattern)) {
        $pattern.Select()
        return "Select"
    }
    $pattern = $null
    if ($El.TryGetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern, [ref]$pattern)) {
        $pattern.Expand()
        return "Expand"
    }
    $r = $El.Current.BoundingRectangle
    $x = [int]($r.X + $r.Width / 2)
    $y = [int]($r.Y + $r.Height / 2)
    [WorkerMouse]::SetCursorPos($x, $y) | Out-Null
    [WorkerMouse]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
    [WorkerMouse]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
    return "Mouse"
}

try {
    if ($Action -eq "find") {
        $res = Find-WithWait
    } elseif ($Action -eq "wait") {
        $res = Find-WithWait
    } elseif ($Action -eq "click") {
        $parent = Get-WindowElement
        if ($null -eq $parent) {
            $res = [ordered]@{ ok = $false; error = "window_not_found"; window = $Window }
        } else {
            $deadline = (Get-Date).AddSeconds([Math]::Max(1, $Timeout))
            $el = $null
            do {
                $el = Get-Control $parent
                if ($null -ne $el) { break }
                Start-Sleep -Milliseconds 250
            } while ((Get-Date) -lt $deadline)
            if ($null -eq $el) {
                $res = [ordered]@{ ok = $false; error = "control_not_found"; window = $Window; name = $Name }
            } else {
                $method = Click-Control $el
                $res = Describe $el
                $res["click_method"] = $method
            }
        }
    } elseif ($Action -eq "focus") {
        $parent = Get-WindowElement
        if ($null -eq $parent) {
            $res = [ordered]@{ ok = $false; error = "window_not_found"; window = $Window }
        } else {
            $h = $parent.Current.NativeWindowHandle
            if ($h -ne 0) {
                [WorkerMouse]::ShowWindow([IntPtr]$h, 9) | Out-Null
                [WorkerMouse]::SetForegroundWindow([IntPtr]$h) | Out-Null
            }
            $res = Describe $parent
        }
    } elseif ($Action -eq "list") {
        $parent = Get-WindowElement
        if ($null -eq $parent) {
            $res = [ordered]@{ ok = $false; error = "window_not_found"; window = $Window }
        } else {
            $all = $parent.FindAll($Scope::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
            $items = @()
            $limit = [Math]::Min($all.Count, 300)
            for ($i = 0; $i -lt $limit; $i++) {
                $d = Describe $all.Item($i)
                if ($null -ne $d) { $items += $d }
            }
            $res = [ordered]@{ ok = $true; count = $all.Count; returned = $items.Count; items = $items }
        }
    }
} catch {
    $res = [ordered]@{ ok = $false; error = $_.Exception.Message; action = $Action }
}

$res | ConvertTo-Json -Compress -Depth 8
