# codevideo

Generador de reels y publicidades con look de cine que corre **entero en tu máquina**.
Escribís un guion en un archivo JSON y sale un MP4 listo para publicar, con escenas animadas,
narración en off, música, subtítulos y acabado cinematográfico.

No usa ninguna IA externa, cuenta ni suscripción:

| Parte | Cómo se hace |
|---|---|
| Escenas y animación | Dibujadas por código (Pillow + numpy) |
| Narración | Voz sintética local con [Piper](https://github.com/OHF-Voice/piper1-gpl) (el modelo se descarga una sola vez) |
| Música y efectos | Sintetizados por código: no hay samples ni licencias de terceros |
| Subtítulos | Generados a partir de la narración |
| Look de cine | Etalonaje, viñeta, grano, barras, transiciones |
| Video final | ffmpeg (H.264 + AAC, −14 LUFS, que es lo que piden las redes) |

## Qué hace y qué no

**Hace:** piezas tipo *motion graphics* — títulos, frases, listas, datos, cierres con llamada a la
acción — sobre fondos animados o sobre **tus propias fotos y videos**, con movimiento de cámara.

**No hace:** inventar imágenes o filmaciones realistas a partir de texto. Eso requiere modelos de
IA generativa pesados, que es justo lo que este proyecto evita. Si querés personas, lugares o tu
espacio de trabajo en pantalla, tenés que filmarlos o fotografiarlos vos y pasarlos como fondo.

La voz es sintética: se entiende bien y suena natural, pero no es un locutor humano. Si querés tu
propia voz, grabate y usala como `musica.archivo` con la voz desactivada (ver más abajo).

## Instalación (una vez)

Necesitás Python 3.10+ y ffmpeg.

```bash
pip install -r requirements.txt
python -m codevideo voces daniela      # descarga la voz (unos 110 MB)
```

## Uso

```bash
python -m codevideo nuevo mi-reel                     # crea guiones/mi-reel.json desde la plantilla
python -m codevideo hoja guiones/mi-reel.json         # una imagen con un cuadro por escena (segundos)
python -m codevideo render guiones/mi-reel.json --borrador   # video rápido a media resolución
python -m codevideo render guiones/mi-reel.json       # video final en salida/mi-reel.mp4
python -m codevideo opciones                          # lista todo lo disponible
```

Probá primero con `python -m codevideo render guiones/demo.json`.
Un reel de 25 s tarda entre uno y dos minutos en una computadora de 4 núcleos.

## El guion

```json
{
  "formato": "reel",
  "estilo": "noche",
  "tipografia": "serif",
  "barras": 0.045,
  "marca": { "nombre": "Tu Marca", "usuario": "@tumarca", "logo": "../medios/logo.png" },
  "voz": { "modelo": "daniela", "velocidad": 0.95 },
  "musica": { "tipo": "ambient", "volumen": 0.6 },
  "subtitulos": true,
  "escenas": [
    { "tipo": "titulo", "texto": "Una frase con *énfasis*.", "narracion": "Lo que dice la voz." }
  ]
}
```

Las palabras entre `*asteriscos*` salen en el color de acento. `\n` fuerza un salto de línea.
Las rutas de archivos son relativas a la carpeta del guion.

### Opciones generales

| Clave | Valores |
|---|---|
| `formato` | `reel` / `historia` (1080×1920), `vertical` (1080×1350), `cuadrado` (1080×1080), `horizontal` (1920×1080) |
| `estilo` | `noche`, `calido`, `bosque`, `violeta`, `noir`, `claro` |
| `colores` | Para usar los colores de tu marca: `{"acento": "#E9B55C", "texto": "#FFFFFF", "fondo": ["#07101A", "#0D1B2E"], "luces": ["#165C7A", "#80481E", "#2C327C"]}` |
| `tipografia` | `serif` (elegante), `sans` (moderna), `trailer` (mayúsculas condensadas) |
| `look` | `cine`, `calido`, `frio`, `noir`, `suave`, `neutro` (por defecto, el del estilo) |
| `grano`, `vineta` | Intensidad, `0` a `2` (por defecto `1`) |
| `barras` | Barras negras de cine: fracción del alto (`0.045`), `0` para quitarlas |
| `transicion` | Transición por defecto: `disolver`, `corte`, `negro`, `destello`, `deslizar` |
| `subtitulos` | `true` / `false` |
| `marca.firma` | `true` para mostrar tu usuario arriba en todas las escenas |

### Voz

`"voz": {"modelo": "daniela", "velocidad": 0.95, "pausa": 0.32}` — o `"voz": false` para no narrar.

| Voz | Acento | Licencia del dataset |
|---|---|---|
| `daniela` | Rioplatense, femenina | CC BY-SA 4.0 |
| `claude` | Mexicano | Apache-2.0 |
| `davefx` | España, masculina | CC0 |

Revisá la licencia de la voz que elijas antes de usarla en publicidad paga.
La escena dura lo que dura su narración; si no hay narración, usa `duracion` o un mínimo razonable.

### Música

`"musica": {"tipo": "ambient", "volumen": 0.6, "efectos": true, "semilla": 7}`

Tipos: `ambient` (contemplativa), `esperanza` (luminosa), `intimo` (mínima), `tension`, `epico`.
Cambiando `semilla` cambia la interpretación. `efectos` agrega golpes graves y barridos en los cortes.
La música baja sola cuando habla la voz.

Para usar un audio tuyo: `"musica": {"archivo": "../medios/mi-tema.mp3"}`. `"musica": false` la quita.

### Escenas

Todas aceptan `narracion`, `duracion`, `transicion` (cómo entra), `fondo`, `subtitulos` y `tamano`
(escala del texto principal, por ejemplo `1.2`).

| Tipo | Campos | Para qué |
|---|---|---|
| `titulo` | `antetitulo`, `texto`, `subtexto` | Gancho, apertura |
| `frase` | `texto`, `autor` | Cita, testimonio |
| `lista` | `titulo`, `items` | Beneficios, pasos |
| `dato` | `numero`, `texto` | Una cifra grande (cuenta sola hasta el número) |
| `plano` | `texto` | Foto/video protagonista con un texto abajo |
| `cierre` | `texto`, `boton`, `usuario` | Llamada a la acción con tu logo |

### Fondos

```json
"fondo": "aurora"
"fondo": {"tipo": "aurora", "intensidad": 1.2, "particulas": true}
"fondo": "gradiente"
"fondo": {"tipo": "color", "color": "#101418"}
"fondo": {"imagen": "../medios/foto.jpg", "movimiento": "zoom-in", "oscurecer": 0.35, "foco": [0.5, 0.3]}
"fondo": {"video": "../medios/clip.mp4", "inicio": 2.0, "oscurecer": 0.4}
```

Movimientos de cámara sobre fotos: `zoom-in`, `zoom-out`, `pan-izq`, `pan-der`, `pan-arriba`,
`pan-abajo`, `auto`. `desenfoque` desenfoca la foto para que el texto mande.
Guardá tus fotos, videos y logo en `medios/`.

## Licencias

Las tipografías incluidas (Inter, DM Serif Display, Bebas Neue) son SIL Open Font License; los
textos están en `codevideo/assets/fonts/`. La música generada es tuya, sin restricciones.
