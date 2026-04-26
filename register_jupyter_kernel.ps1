# One-time: install ipykernel into .venv_notebook_demo and register a Jupyter / Cursor kernel.
# Notebook libraries install in cells via %pip as needed; ipykernel is required for any Jupyter kernel.
#Requires -Version 5.0
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $ProjectRoot ".venv_notebook_demo"
$Python = Join-Path $Venv "Scripts\python.exe"

# Python 3.11 is required
$Py311 = & py -3.11 -c "import sys; print(sys.executable)" 2>$null
if (-not $Py311) { throw "Python 3.11 not found. Install 64-bit from https://www.python.org/downloads/ (e.g. 3.11.9) and check: py -0p" }

if (-not (Test-Path $Python)) {
    Write-Host "Creating venv (Python 3.11) in .venv_notebook_demo ..."
    py -3.11 -m venv $Venv
    if (-not (Test-Path $Python)) { throw "python.exe not found: $Python" }
} else {
    $cfg = Join-Path $Venv "pyvenv.cfg"
    if (Test-Path $cfg) {
        $verLine = (Get-Content -LiteralPath $cfg | Where-Object { $_ -match '^\s*version\s*=\s*' } | Select-Object -First 1)
        if ($verLine -and $verLine -notmatch 'version\s*=\s*3\.11') {
            Write-Warning "Existing venv is not 3.11 ($verLine). Remove the folder or rename it, then re-run this script to recreate venv with Python 3.11."
        }
    }
}

$KernelName = "ai-agents-notebook-demo"
$DisplayName  = "Python 3.11 (ai-agents .venv_notebook_demo)"

& $Python -m pip install -U pip ipykernel
& $Python -m ipykernel install --user --name=$KernelName --display-name=$DisplayName

# Cursor / VS Code (Electron) can crash on kernel specs whose argv[0] contains non-ASCII
# in the path (e.g. Cyrillic folder names). Rewrite to Windows 8.3 short path.
$KernelJson = Join-Path $env:APPDATA "jupyter\kernels\$KernelName\kernel.json"
try {
    $fso = New-Object -ComObject Scripting.FileSystemObject
    $ShortExe = $fso.GetFile( (Resolve-Path -LiteralPath $Python).Path ).ShortPath
    $patch = @"
import json, pathlib, sys, os
p = pathlib.Path(sys.argv[1])
exe = sys.argv[2]
d = json.loads(p.read_text(encoding="utf-8"))
d["argv"][0] = exe
# Some Electron/IDE builds crash on debug adapter hooks when this is true; keep kernel runnable.
d.setdefault("metadata", {})["debugger"] = False
# Verify short path is actually executable
if not os.path.isfile(exe):
    raise SystemExit("Kernel argv[0] is not a file: " + repr(exe))
p.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
"@
    $patchFile = Join-Path $env:TEMP "ipykernel_shortpath_$(Get-Random).py"
    Set-Content -LiteralPath $patchFile -Value $patch -Encoding utf8
    & $Python $patchFile $KernelJson $ShortExe
    Remove-Item -LiteralPath $patchFile -Force
    Write-Host "Patched kernel argv[0] to 8.3 path (avoids non-ASCII path issues in some IDEs)."
} catch {
    Write-Warning "Could not set short path in kernel.json (you may need to re-run if the IDE still crashes on kernel select): $_"
}

Write-Host "Done. Kernel name: $KernelName — display name: $DisplayName"
Write-Host "Choose it in the notebook kernel picker (Cursor / Jupyter / VS Code)."
