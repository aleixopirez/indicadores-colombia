"""
Paso 3 — HDFS.

    python -m datalake consumir                 # Kafka -> HDFS hasta vaciar los tópicos
    python -m datalake consumir --continuo      # se queda escuchando (Ctrl+C para salir)
    python -m datalake ls /datalake/raw/banrep
    python -m datalake resumen                  # archivos y tamaño por dataset
    python -m datalake cat <ruta> --lineas 3
    python -m datalake subir referencia/gobiernos.csv /datalake/referencia/gobiernos/gobiernos.csv
"""
import argparse
import logging
import sys

from datalake import config


def _tamano(n: int) -> str:
    for unidad in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unidad}" if unidad == "B" else f"{n:.1f} {unidad}"
        n /= 1024
    return f"{n:.1f} TB"


def cmd_ls(hdfs, ruta):
    for e in hdfs.listar(ruta):
        tipo = "d" if e["type"] == "DIRECTORY" else "-"
        print(f"{tipo} {_tamano(e['length']):>10}  {e['pathSuffix']}")


def cmd_resumen(hdfs):
    raiz = config.RAIZ_RAW
    fuentes = hdfs.listar(raiz)
    print(f"{'fuente/dataset':<42}{'archivos':>10}{'tamaño':>12}")
    total_arch = total_bytes = 0
    for fuente in fuentes:
        if fuente["type"] != "DIRECTORY":
            continue
        for ds in hdfs.listar(f"{raiz}/{fuente['pathSuffix']}"):
            s = hdfs.resumen(f"{raiz}/{fuente['pathSuffix']}/{ds['pathSuffix']}")
            nombre = f"{fuente['pathSuffix']}/{ds['pathSuffix']}"
            print(f"{nombre:<42}{s['fileCount']:>10}{_tamano(s['length']):>12}")
            total_arch += s["fileCount"]
            total_bytes += s["length"]
    print(f"{'TOTAL':<42}{total_arch:>10}{_tamano(total_bytes):>12}")


def cmd_cat(hdfs, ruta, lineas):
    texto = hdfs.leer(ruta).decode("utf-8").splitlines()
    for linea in texto[:lineas]:
        print(linea[:300])
    print(f"... ({len(texto)} líneas en total)")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="datalake", description="Paso 3: HDFS")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="accion", required=True)

    p_c = sub.add_parser("consumir", help="Kafka -> HDFS")
    p_c.add_argument("--continuo", action="store_true")
    p_ls = sub.add_parser("ls", help="lista una carpeta de HDFS")
    p_ls.add_argument("ruta", nargs="?", default=config.RAIZ_RAW)
    sub.add_parser("resumen", help="archivos y tamaño por dataset")
    p_cat = sub.add_parser("cat", help="muestra las primeras líneas de un archivo")
    p_cat.add_argument("ruta")
    p_cat.add_argument("--lineas", type=int, default=3)
    p_sub = sub.add_parser("subir", help="copia un archivo local a HDFS")
    p_sub.add_argument("local")
    p_sub.add_argument("ruta_hdfs")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    if not args.verbose:
        logging.getLogger("kafka").setLevel(logging.CRITICAL)

    import requests
    from datalake.webhdfs import ErrorHDFS, WebHDFS
    hdfs = WebHDFS()
    log = logging.getLogger("datalake")
    try:
        if args.accion == "consumir":
            from datalake import consumidor_hdfs
            consumidor_hdfs.ejecutar(continuo=args.continuo, hdfs=hdfs)
        elif args.accion == "ls":
            cmd_ls(hdfs, args.ruta)
        elif args.accion == "resumen":
            cmd_resumen(hdfs)
        elif args.accion == "cat":
            cmd_cat(hdfs, args.ruta, args.lineas)
        elif args.accion == "subir":
            n = hdfs.subir_archivo(args.local, args.ruta_hdfs)
            log.info("%s -> %s (%d bytes)", args.local, args.ruta_hdfs, n)
    except KeyboardInterrupt:
        log.info("Detenido por el usuario. Lo ya escrito quedó confirmado en Kafka.")
    except requests.ConnectionError:
        log.error("No hay conexión con HDFS en %s. ¿Está corriendo? Prueba: "
                  "docker compose --profile kafka --profile hdfs up -d", config.WEBHDFS_URL)
        return 1
    except ErrorHDFS as e:
        log.error("HDFS respondió con error: %s", e)
        return 1
    except Exception as e:  # noqa: BLE001
        from kafka.errors import NoBrokersAvailable
        if isinstance(e, NoBrokersAvailable):
            log.error("No hay conexión con Kafka en %s.", config.KAFKA_BOOTSTRAP)
        else:
            log.error("%s: %s", type(e).__name__, e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
