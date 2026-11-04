#!/usr/bin/env python3
"""CLI para listar las tareas (project.task) asignadas a un usuario de Odoo 17.

Solo usa la biblioteca estandar de Python (3.8 o superior): no hay que
instalar nada. Se conecta por XML-RPC (/xmlrpc/2), la API externa de Odoo 17.

Las credenciales se leen de un fichero .env (ver .env.template), junto al
script o en el directorio actual. Las variables de entorno del sistema tienen
prioridad sobre el .env:

  ODOO_URL        p. ej. https://miempresa.odoo.com
  ODOO_DB         nombre de la base de datos
  ODOO_LOGIN      usuario con el que se conecta (normalmente su email)
  ODOO_PASSWORD   contrasena del usuario, o una clave de API de Odoo
"""
import argparse
import csv
import json
import os
import sys
import xmlrpc.client

CAMPOS = ["id", "name", "project_id", "stage_id", "date_deadline", "priority"]
VARIABLES = ["ODOO_URL", "ODOO_DB", "ODOO_LOGIN", "ODOO_PASSWORD"]


class OdooError(Exception):
    """Error devuelto por Odoo o por la conexion."""


def cargar_env():
    """Lee ficheros .env (KEY=VALOR) sin pisar las variables ya definidas."""
    rutas = [os.path.join(os.getcwd(), ".env"),
             os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")]
    for ruta in dict.fromkeys(rutas):
        if not os.path.isfile(ruta):
            continue
        with open(ruta, encoding="utf-8") as fichero:
            for linea in fichero:
                linea = linea.strip()
                if not linea or linea.startswith("#") or "=" not in linea:
                    continue
                clave, valor = linea.split("=", 1)
                clave, valor = clave.strip(), valor.strip()
                if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
                    valor = valor[1:-1]
                os.environ.setdefault(clave, valor)


class Cliente:
    """Cliente minimo XML-RPC para Odoo (execute_kw)."""

    def __init__(self, url, db, login, password):
        url = url.strip().rstrip("/")
        if "://" not in url:
            url = "https://" + url  # xmlrpc.client exige el esquema
        base = url + "/xmlrpc/2"
        self.db, self.password = db, password
        try:
            self.objeto = xmlrpc.client.ServerProxy(base + "/object", allow_none=True)
            self.uid = xmlrpc.client.ServerProxy(base + "/common").authenticate(
                db, login, password, {}
            )
        except xmlrpc.client.Fault as err:
            raise OdooError(err.faultString.strip().splitlines()[-1])
        except (OSError, xmlrpc.client.Error) as err:
            raise OdooError("No se pudo conectar con %s: %s" % (url, err))
        if not self.uid:
            raise OdooError("Autenticacion fallida: revise ODOO_LOGIN, ODOO_PASSWORD y ODOO_DB.")

    def llamar(self, modelo, metodo, args=None, **kwargs):
        try:
            return self.objeto.execute_kw(
                self.db, self.uid, self.password, modelo, metodo, args or [], kwargs
            )
        except xmlrpc.client.Fault as err:
            raise OdooError(err.faultString.strip().splitlines()[-1])
        except OSError as err:
            raise OdooError("Error de conexion: %s" % err)


def resolver_usuario(cliente, valor):
    """Devuelve (id, nombre) del usuario a partir de id, login, email o nombre."""
    if valor is None:
        uid = cliente.uid
    elif valor.isdigit():
        uid = int(valor)
    else:
        for campo, operador in (("login", "="), ("email", "="), ("name", "ilike")):
            ids = cliente.llamar("res.users", "search",
                                 [[[campo, operador, valor]]], limit=2)
            if len(ids) == 1:
                uid = ids[0]
                break
            if len(ids) > 1:
                raise OdooError("'%s' coincide con varios usuarios; use el login o el id." % valor)
        else:
            raise OdooError("No se encontro ningun usuario para '%s'." % valor)
    usuario = cliente.llamar("res.users", "read", [[uid]], fields=["name"])
    if not usuario:
        raise OdooError("El usuario %s no existe o no es visible." % uid)
    return uid, usuario[0]["name"]


def buscar_tareas(cliente, uid, incluir_cerradas, proyecto, limite):
    # Odoo 17: asignacion multiple en user_ids; estado en state.
    dominio = [["user_ids", "in", [uid]]]
    if not incluir_cerradas:
        dominio.append(["state", "not in", ["1_done", "1_canceled"]])
    if proyecto:
        dominio.append(["project_id.name", "ilike", proyecto])
    return cliente.llamar(
        "project.task", "search_read", [dominio],
        fields=CAMPOS, order="date_deadline asc, id asc", limit=limite,
    )


def nombre(valor):
    """Los many2one llegan como [id, nombre] o False."""
    if isinstance(valor, (list, tuple)) and len(valor) == 2:
        return valor[1]
    return "" if valor in (False, None) else str(valor)


def fila(tarea):
    return {
        "id": tarea["id"],
        "tarea": tarea.get("name") or "",
        "proyecto": nombre(tarea.get("project_id")),
        "etapa": nombre(tarea.get("stage_id")),
        "fecha_limite": (tarea.get("date_deadline") or "")[:10],
    }


def imprimir_tabla(filas):
    if not filas:
        print("Sin tareas.")
        return
    cols = ["id", "tarea", "proyecto", "etapa", "fecha_limite"]
    ancho = {c: max(len(c), *(len(str(f[c])) for f in filas)) for c in cols}
    ancho["tarea"] = min(ancho["tarea"], 60)
    ancho["proyecto"] = min(ancho["proyecto"], 30)
    print("  ".join(c.upper().ljust(ancho[c]) for c in cols))
    for f in filas:
        print("  ".join(str(f[c])[:ancho[c]].ljust(ancho[c]) for c in cols))


def leer_argumentos():
    p = argparse.ArgumentParser(
        description="Lista las tareas de Odoo 17 asignadas a un usuario.",
        epilog=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("usuario", nargs="?",
                   help="id, login, email o nombre del usuario (por defecto, el usuario conectado)")
    p.add_argument("--proyecto", help="filtrar por nombre de proyecto (contiene)")
    p.add_argument("--todas", action="store_true", help="incluir tareas cerradas o canceladas")
    p.add_argument("--limite", type=int, default=200, help="maximo de tareas (200 por defecto)")
    formato = p.add_mutually_exclusive_group()
    formato.add_argument("--json", action="store_true", help="salida en JSON")
    formato.add_argument("--csv", action="store_true", help="salida en CSV")
    return p.parse_args()


def main():
    args = leer_argumentos()
    cargar_env()
    faltan = [v for v in VARIABLES if not os.environ.get(v)]
    if faltan:
        sys.exit("Faltan variables en .env o en el entorno: %s" % ", ".join(faltan))
    try:
        cliente = Cliente(*(os.environ[v] for v in VARIABLES))
        uid, nombre_usuario = resolver_usuario(cliente, args.usuario)
        tareas = buscar_tareas(cliente, uid, args.todas, args.proyecto, args.limite)
    except OdooError as err:
        sys.exit("Error: %s" % err)

    filas = [fila(t) for t in tareas]
    if args.json:
        print(json.dumps({"usuario": nombre_usuario, "tareas": filas}, ensure_ascii=False, indent=2))
    elif args.csv:
        escritor = csv.DictWriter(sys.stdout, fieldnames=list(filas[0]) if filas else ["id"])
        escritor.writeheader()
        escritor.writerows(filas)
    else:
        print("Tareas de %s (%d)\n" % (nombre_usuario, len(filas)))
        imprimir_tabla(filas)


if __name__ == "__main__":
    main()
