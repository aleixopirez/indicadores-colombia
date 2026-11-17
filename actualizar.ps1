<#
  Actualiza todo el pipeline con datos recientes y publica el dashboard.

  Uso (en la terminal de VS Code, dentro de la carpeta del proyecto):
      .\actualizar.ps1                    # últimos 45 días + publica en GitHub Pages
      .\actualizar.ps1 -Desde 2026-10-01  # desde una fecha
      .\actualizar.ps1 -Reels             # además genera los reels PNG/MP4
      .\actualizar.ps1 -SinPublicar       # no hace git push

  Recorre los pasos en orden, encendiendo solo los contenedores que cada paso
  necesita (el equipo tiene 8 GB de RAM):
      1 Ingesta -> 2 Kafka -> 3 HDFS -> 4 PySpark -> 6 PostgreSQL -> 7 HTML -> GitHub
  Hive (paso 5) no hace falta para actualizar: sus tablas externas leen la
  misma carpeta curada de HDFS.

  Volver a traer días que ya estaban no duplica nada: PySpark elimina los
  registros repetidos al curar (paso 4).
#>
param(
    [string]$Desde = (Get-Date).AddDays(-45).ToString("yyyy-MM-dd"),
    [switch]$Reels,
    [switch]$SinPublicar
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$inicio = Get-Date

function Paso([string]$titulo) {
    Write-Host ""
    Write-Host "=== $titulo ===" -ForegroundColor Yellow
}

# Ejecuta un comando externo y se detiene si falla
function Correr([scriptblock]$comando) {
    $texto = $ExecutionContext.InvokeCommand.ExpandString($comando.ToString().Trim())
    Write-Host "> $texto" -ForegroundColor DarkGray
    & $comando
    if ($LASTEXITCODE -ne 0) { throw "Falló: $comando (código $LASTEXITCODE)" }
}

if (-not $env:VIRTUAL_ENV) { . .\.venv\Scripts\Activate.ps1 }
$anioBM = (Get-Date).Year - 5     # el Banco Mundial revisa cifras de años recientes

Paso "1/6 Ingesta desde las fuentes (desde $Desde)"
Correr { python -m ingesta trm --desde $Desde }
Correr { python -m ingesta banrep --desde $Desde }
# El Banco Mundial publica datos anuales y su API a veces se cae (error 503).
# Si falla, se sigue con lo que ya hay en el data lake en lugar de detener todo.
try {
    Correr { python -m ingesta banco_mundial --desde $anioBM }
} catch {
    Write-Host "AVISO: el Banco Mundial no respondió; se usan sus datos anteriores. ($_)" -ForegroundColor DarkYellow
}

Paso "2/6 Kafka y 3/6 HDFS"
Correr { docker compose up -d --wait kafka namenode datanode }
Correr { python -m streaming producir }
Correr { python -m datalake consumir }
Correr { docker compose stop kafka }

Paso "4/6 PySpark: curar"
Correr { docker compose run --rm spark }

Paso "5/6 PostgreSQL: zona de servicio"
Correr { docker compose up -d --wait namenode datanode postgres }
Correr { docker compose run --rm spark-servir }

Paso "6/6 Dashboard HTML"
Correr { python -m visualizacion generar }
Correr { python -m visualizacion publicar }
if ($Reels) { Correr { python -m visualizacion capturar } }

if (-not $SinPublicar) {
    Paso "Publicar en GitHub Pages"
    Correr { git add docs }
    git diff --cached --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Host "El dashboard no cambió: no hay nada que publicar."
    } else {
        $hoy = Get-Date -Format "yyyy-MM-dd"
        Correr { git commit -m "Actualiza dashboard ($hoy)" }
        Correr { git push }
    }
}

# Libera memoria: deja encendido solo PostgreSQL (para Power BI)
Correr { docker compose stop namenode datanode }

$min = [math]::Round(((Get-Date) - $inicio).TotalMinutes, 1)
Write-Host ""
Write-Host "Listo en $min min. Dashboard: salida\dashboard.html" -ForegroundColor Green
if (-not $SinPublicar) { Write-Host "En línea en 1-2 minutos: https://aleixopirez.github.io/indicadores-colombia/" -ForegroundColor Green }
Write-Host "Power BI: abra powerbi\indicadores.pbix y pulse Actualizar." -ForegroundColor Green
