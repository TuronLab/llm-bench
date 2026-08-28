# Análisis técnico: arquitectura de una plataforma de recomendaciones

Estás diseñando una plataforma de recomendaciones de contenido para una aplicación con millones de usuarios. El sistema debe combinar recomendaciones personalizadas y contenido popular, responder rápidamente y seguir funcionando aunque algunos servicios estén degradados.

## Contexto

La plataforma recibe eventos de interacción —impresiones, reproducciones, búsquedas, valoraciones positivas, valoraciones negativas y abandonos— desde aplicaciones móviles y web. Los eventos llegan a una cola distribuida y se conservan para poder reprocesarlos. Un pipeline de streaming calcula señales recientes, mientras que un pipeline batch genera embeddings y modelos actualizados varias veces al día.

El catálogo contiene vídeos, artículos y podcasts. Cada elemento tiene idioma, categorías, fecha de publicación, duración, restricciones geográficas y señales de calidad editorial. Algunos contenidos deben promocionarse durante campañas, pero nunca deben superar los límites de seguridad ni aparecer a usuarios para los que no sean apropiados.

## Requisitos funcionales

1. Genera una lista de candidatos suficientemente grande para que las etapas posteriores puedan filtrarla y reordenarla.
2. Combina señales de largo plazo, como los temas preferidos por el usuario, con señales de corto plazo, como la sesión actual.
3. Evita recomendar repetidamente el mismo elemento o elementos muy similares entre sí.
4. Permite explorar contenido nuevo sin destruir la relevancia esperada.
5. Explica qué señales principales influyeron en una recomendación.
6. Respeta idioma, edad, región, disponibilidad, consentimiento y reglas de contenido.
7. Permite retirar rápidamente un elemento del catálogo sin esperar al siguiente entrenamiento batch.

## Requisitos no funcionales

- El p95 de la petición completa debe mantenerse por debajo de 150 milisegundos.
- El sistema debe soportar picos de diez veces el tráfico habitual.
- Las recomendaciones deben poder calcularse con datos parcialmente obsoletos cuando una dependencia no esté disponible.
- Los equipos de datos deben poder reproducir por qué se mostró una lista concreta en una fecha determinada.
- Las métricas deben distinguir calidad, diversidad, cobertura, latencia y errores por versión del modelo y segmento de usuario.

## Tarea

Escribe una propuesta técnica completa, pero concreta, para este sistema. Incluye estas secciones:

1. Arquitectura general y responsabilidades de cada componente.
2. Flujo online de una petición, desde la recepción hasta la respuesta.
3. Pipelines offline y nearline, incluyendo almacenamiento y versionado.
4. Estrategia de generación de candidatos y re-ranking.
5. Gestión de frescura, exploración, diversidad y restricciones de seguridad.
6. Diseño de cachés y degradación controlada ante fallos.
7. Observabilidad: logs, trazas, métricas y auditoría de decisiones.
8. Evaluación offline y experimento A/B online.
9. Riesgos principales y decisiones que deberían validarse con una prueba de carga o un prototipo.

Compara al menos dos alternativas para el almacenamiento de features y explica cuándo elegirías cada una. Incluye un ejemplo de contrato JSON simplificado para la respuesta del endpoint de recomendaciones. No inventes resultados de rendimiento: indica qué medirías y cómo diseñarías la prueba.
