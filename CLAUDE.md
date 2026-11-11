# codevideo — guía para Claude

Generador local de reels/publicidades: guion JSON → MP4. Sin IA ni servicios externos; no proponer
ni integrar APIs de generación de imagen/video/voz salvo pedido explícito del usuario.

## Cuando el usuario pide un video

1. Escribir el guion en `guiones/<nombre>.json` (formato y opciones en `README.md`;
   `python -m codevideo opciones` lista los valores válidos).
2. `python -m codevideo hoja guiones/<nombre>.json` y mirar la imagen resultante para revisar
   maquetado y legibilidad antes de renderizar.
3. `python -m codevideo render guiones/<nombre>.json` → `salida/<nombre>.mp4` (no se versiona).
   Enviarle el MP4 al usuario.

Si falta la voz: `pip install -r requirements.txt && python -m codevideo voces daniela`.

## Criterio para los guiones

- No inventar datos, cifras, testimonios ni credenciales del usuario. Si falta información, preguntar.
- Una idea por escena. Reel típico: gancho → problema → propuesta → prueba → una sola acción (20–35 s).
- La narración se escribe para el oído: frases cortas, números en letras si se leen raro.
- El texto en pantalla resume; no repite la narración palabra por palabra (para eso están los subtítulos).
- En el cierre, `"subtitulos": false` si el botón ya dice lo mismo que la voz.
- Material del usuario (fotos, videos, logo) va en `medios/`.

## Código

- `guion.py` catálogos y validación · `escenas.py` tipos de escena · `texto.py` maquetado y capas
- `fondos.py` fondos · `post.py` look de cine · `voz.py` Piper · `musica.py` síntesis · `audio.py` mezcla
- `render.py` línea de tiempo, subtítulos, transiciones y codificación
- Todo el dibujo escala con `u = min(W, H) / 1080`. Los cuadros son float32 0–255 hasta `Post.aplicar`.
- Probar cambios visuales con `hoja` o `cuadro -t`, y `render --borrador` para movimiento y audio.
