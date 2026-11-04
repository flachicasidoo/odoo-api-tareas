# odoo-api-tareas

CLI en Python (solo biblioteca estandar) que lista las tareas de Odoo 17
asignadas a un usuario, por XML-RPC. Acompana a la guia
`Guia_API_Odoo_tareas.pdf`.

## Configuracion

```sh
cp .env.template .env
# edite .env: ODOO_URL, ODOO_DB, ODOO_LOGIN y ODOO_PASSWORD
```

`ODOO_PASSWORD` admite la contrasena del usuario o una clave de API
(Preferencias > Seguridad de la cuenta). El `.env` esta en `.gitignore`.

## Uso

```sh
python3 odoo_tareas.py                      # tareas abiertas del usuario conectado
python3 odoo_tareas.py luis@miempresa.com   # de otro usuario (id, login, email o nombre)
python3 odoo_tareas.py luis --todas --proyecto "Web" --csv
python3 odoo_tareas.py --help
```
