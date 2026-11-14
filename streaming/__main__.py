"""
Paso 2 — Kafka.

    python -m streaming crear-topicos
    python -m streaming producir                      # todo lo pendiente
    python -m streaming producir --fuente banrep
    python -m streaming producir --reenviar           # ignora los .kafka_ok
    python -m streaming consumir raw.banrep --max 5
"""
import argparse
import logging
import sys

from streaming import config


def main(argv=None):
    parser = argparse.ArgumentParser(prog="streaming", description="Paso 2: Kafka")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="accion", required=True)

    sub.add_parser("crear-topicos", help="crea los tópicos raw.* si no existen")

    p_prod = sub.add_parser("producir", help="publica los .jsonl pendientes")
    p_prod.add_argument("--fuente", choices=list(config.TOPICOS))
    p_prod.add_argument("--reenviar", action="store_true",
                        help="vuelve a enviar archivos ya marcados como enviados")

    p_cons = sub.add_parser("consumir", help="muestra mensajes de un tópico")
    p_cons.add_argument("topico", choices=list(config.TOPICOS.values()))
    p_cons.add_argument("--max", type=int, default=5, help="mensajes a imprimir")
    p_cons.add_argument("--grupo", help="consumer group (guarda la posición leída)")
    p_cons.add_argument("--solo-nuevos", action="store_true",
                        help="empieza desde el final del tópico")

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    # kafka-python imprime cada reintento de conexión como ERROR. Nuestro código
    # ya reporta los fallos con un mensaje claro; con -v se ve todo el detalle.
    if not args.verbose:
        logging.getLogger("kafka").setLevel(logging.CRITICAL)

    try:
        if args.accion == "crear-topicos":
            from streaming import topicos
            topicos.crear_topicos()
        elif args.accion == "producir":
            from streaming import productor
            productor.ejecutar(args.fuente, args.reenviar)
        elif args.accion == "consumir":
            from streaming import consumidor
            consumidor.ejecutar(args.topico, args.max,
                                desde_inicio=not args.solo_nuevos, grupo=args.grupo)
    except Exception as e:  # noqa: BLE001
        from kafka.errors import NoBrokersAvailable
        if isinstance(e, NoBrokersAvailable):
            logging.getLogger("streaming").error(
                "No hay conexión con Kafka en %s. ¿Está corriendo? "
                "Prueba: docker compose --profile kafka up -d", config.KAFKA_BOOTSTRAP)
        else:
            logging.getLogger("streaming").error("%s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
