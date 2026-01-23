# Questions Translation Service

Microservicio para traducir archivos Excel de preguntas usando la API de DeepL.

## Características

- ✅ Traduce archivos Excel con preguntas
- ✅ Soporta 30+ idiomas de destino
- ✅ Traducción batch a múltiples idiomas (devuelve ZIP)
- ✅ Preserva la estructura y formato del Excel
- ✅ Autenticación con API Key
- ✅ Rate limiting configurable
- ✅ Reintentos automáticos con backoff exponencial
- ✅ Logging estructurado (JSON/text)
- ✅ Health checks para Kubernetes
- ✅ Docker ready

## Requisitos

- Python 3.11+
- DeepL API Key ([obtener aquí](https://www.deepl.com/pro-api))

## Instalación

### Desarrollo local

```bash
cd question-translation
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configurar variables de entorno
cp .env.example .env
# Editar .env con tu DEEPL_API_KEY y API_KEY
```

### Docker

```bash
# Construir y ejecutar
docker-compose up -d

# Ver logs
docker-compose logs -f
```

## Ejecución

```bash
# Desarrollo (con reload)
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Producción
uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4
```

El servidor estará disponible en: http://localhost:8000

## Documentación API

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Endpoints

| Método | Endpoint | Auth | Descripción |
|--------|----------|------|-------------|
| GET | `/` | No | Health check básico |
| GET | `/health` | No | Health check detallado |
| GET | `/live` | No | Kubernetes liveness probe |
| GET | `/ready` | No | Kubernetes readiness probe |
| GET | `/languages` | No | Lista de idiomas soportados |
| GET | `/usage` | Sí | Estadísticas de uso DeepL |
| POST | `/translate` | Sí | Traducir a 1 idioma → Excel |
| POST | `/translate/batch` | Sí | Traducir a N idiomas → ZIP |
| POST | `/translate/info` | Sí | Traducir → metadata JSON |
| POST | `/translate/batch/info` | Sí | Traducir batch → metadata JSON |

## Autenticación

Si `API_KEY` está configurado en `.env`, todos los endpoints de traducción requieren el header:

```
X-API-Key: tu_api_key
```

## Formato del Excel

El archivo Excel debe contener una hoja llamada **`Questions`** con:

- **Celda C3**: Código de idioma origen (ej: "es")
- **Fila 6**: Headers
- **Fila 7+**: Datos

| Columna | Se traduce | Descripción |
|---------|------------|-------------|
| A | ❌ | Número de pregunta |
| D | ✅ | Pregunta |
| E | ✅ | Respuesta correcta |
| F | ✅ | Opción 1 |
| G | ✅ | Opción 2 |
| H | ✅ | Opción 3 |

## Códigos de Idioma

Usa los códigos internos (no los de DeepL):

| Código | Idioma | Código | Idioma |
|--------|--------|--------|--------|
| es | Español | nl | Holandés |
| en | Inglés (US) | zh | Chino |
| it | Italiano | jp | Japonés |
| fr | Francés | pl | Polaco |
| de | Alemán | tr | Turco |
| pt | Portugués | hu | Húngaro |
| pt_BR | Brasileño | bg | Búlgaro |
| ru | Ruso | ... | ... |

Ver `/languages` para la lista completa.

## Ejemplos de Uso

### Traducir a un idioma

```bash
curl -X POST "http://localhost:8000/translate" \
  -H "X-API-Key: tu_api_key" \
  -F "file=@preguntas.xlsx" \
  -F "target_language=en" \
  -o preguntas_en.xlsx
```

### Traducir a múltiples idiomas

```bash
curl -X POST "http://localhost:8000/translate/batch" \
  -H "X-API-Key: tu_api_key" \
  -F "file=@preguntas.xlsx" \
  -F "target_languages=en,fr,de,it" \
  -o translations.zip
```

### Con Python

```python
import requests

# Traducir a un idioma
with open("preguntas.xlsx", "rb") as f:
    response = requests.post(
        "http://localhost:8000/translate",
        files={"file": f},
        data={"target_language": "en"},
        headers={"X-API-Key": "tu_api_key"}
    )

with open("preguntas_en.xlsx", "wb") as f:
    f.write(response.content)

# Traducir a múltiples idiomas
with open("preguntas.xlsx", "rb") as f:
    response = requests.post(
        "http://localhost:8000/translate/batch",
        files={"file": f},
        data={"target_languages": "en,fr,de"},
        headers={"X-API-Key": "tu_api_key"}
    )

with open("translations.zip", "wb") as f:
    f.write(response.content)
```

## Configuración

Variables de entorno (ver `.env.example`):

| Variable | Descripción | Default |
|----------|-------------|---------|
| `DEEPL_API_KEY` | API key de DeepL | (requerido) |
| `API_KEY` | API key para autenticación | (vacío = sin auth) |
| `RATE_LIMIT_REQUESTS` | Requests por ventana | 100 |
| `RATE_LIMIT_WINDOW` | Ventana en segundos | 60 |
| `MAX_FILE_SIZE_MB` | Tamaño máximo de archivo | 10 |
| `MAX_LANGUAGES_PER_BATCH` | Idiomas máx por batch | 20 |
| `LOG_LEVEL` | Nivel de log | INFO |
| `LOG_FORMAT` | Formato: json/text | json |

## Estructura del Proyecto

```
question-translation/
├── src/
│   ├── main.py                 # FastAPI app
│   ├── config/
│   │   ├── settings.py         # Configuración
│   │   ├── languages.py        # Mapeo de idiomas
│   │   └── logging.py          # Logging estructurado
│   ├── middleware/
│   │   ├── auth.py             # Autenticación API Key
│   │   └── rate_limit.py       # Rate limiting
│   ├── schemas/
│   │   └── translation.py      # Esquemas Pydantic
│   └── services/
│       ├── translator.py       # Servicio DeepL con reintentos
│       └── excel_processor.py  # Procesamiento Excel
├── tests/
│   ├── conftest.py
│   ├── test_api.py
│   └── test_languages.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── requirements-dev.txt
└── .env.example
```

## Tests

```bash
# Instalar dependencias de desarrollo
pip install -r requirements-dev.txt

# Ejecutar tests
pytest tests/ -v
```

## Notas de Producción

- Configura `API_KEY` para proteger los endpoints
- Usa `LOG_FORMAT=json` para integración con sistemas de logs
- Los health checks están en `/health`, `/live`, `/ready`
- Rate limiting es in-memory (usa Redis para múltiples instancias)
- Los reintentos tienen backoff exponencial (1s, 2s, 4s...)
