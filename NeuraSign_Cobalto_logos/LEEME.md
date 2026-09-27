# NeuraSign · Identidad 05 / Cobalto

Símbolo 05 y paleta cobalto elegidos por el usuario el 26 de septiembre de 2026.

## Colores

| Uso | Color |
| --- | --- |
| Símbolo y acento principal | Cobalto `#2854E8` |
| Nombre y texto principal | Tinta `#131A2A` |
| Fondo claro | Blanco frío `#F5F7FC` |
| Fondo oscuro | Noche `#0D1321` |
| Símbolo sobre fondo oscuro | Cobalto luminoso `#6C8BFF` |
| Nombre sobre fondo oscuro | Blanco `#FFFFFF` |

## Archivos

Cada carpeta de `svg` contiene isotipo, logotipo, imagotipo horizontal, imagotipo vertical y favicon. Todos tienen fondo transparente.

- `principal`: símbolo cobalto y nombre tinta.
- `fondo-oscuro`: símbolo azul luminoso y nombre blanco.
- `monocromo`: marca completa en tinta.
- `blanco`: marca completamente blanca.

`brand-tokens.css` y `brand-tokens.json` contienen los colores exactos para producto y documentos.

## Construcción

Dos piezas idénticas. Vértices de la primera: `(0,42)`, `(64,0)`, `(64,136)`, `(0,178)`. La segunda se desplaza `(76,62)`. Radio de esquina: `3`. Separación horizontal: `12`. Caja ideal: `140 × 240`. Espacio de protección: `32` unidades.

La separación del símbolo y el nombre en el imagotipo horizontal es `100` unidades. La altura visible del nombre es `128`, centrada respecto al símbolo. Mantener siempre las proporciones.

El nombre está reconstruido con Inter Bold de Rasmus Andersson y convertido a contornos. Los logos no necesitan fuentes instaladas y no contienen imágenes incrustadas. Inter utiliza SIL Open Font License 1.1: https://rsms.me/inter/ y https://openfontlicense.org/ .

Para regenerar los veinte SVG: `python3 build_logos.py`. Solo requiere Python y los contornos incluidos en `wordmark_paths.json`.

Usar el isotipo en espacios pequeños. No estirar, girar las piezas ni modificar su separación. El símbolo mantiene color en las versiones principales; el nombre permanece oscuro o blanco según el fondo.
