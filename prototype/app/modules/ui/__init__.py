"""Blueprint de vistas HTML (PWA): páginas del jugador y del público.

Capa de presentación **sin lógica de negocio**: cada vista llama a los
servicios de su módulo (``iam``, ``combat``, ``history``, ``public_api``) y
renderiza un template. Las escrituras que el usuario dispara desde una página
(viajar, confirmar) se hacen con **fetch** contra la API JSON existente
(Sprint 7.6): esta capa solo entrega HTML y el shell de la PWA.

Rutas (Sprint 7): ``/`` y ``/ranking`` públicas; ``/login``, ``/registro``,
``/salir``, ``/reportar``, ``/pendientes`` y ``/historial`` para la sesión.
"""
