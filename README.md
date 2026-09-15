# Monitor de sitios con aviso por WhatsApp

Revisa una lista de sitios web cada 5 minutos desde GitHub Actions y te avisa
por WhatsApp (vía CallMeBot) solo cuando un sitio cambia de estado: cuando se
cae, y cuando se recupera. No manda avisos repetidos mientras sigue caído.

## 1. Activar CallMeBot (2 minutos)

1. En tu WhatsApp, agrega el contacto de CallMeBot (el número está en
   https://www.callmebot.com/blog/free-api-whatsapp-messages/, puede cambiar
   de vez en cuando por límites de capacidad — si no aparece, revisa esa
   página para el número actualizado).
2. Mándale por WhatsApp el mensaje exacto: `I allow callmebot to send me messages`
3. En menos de 2 minutos te responde con tu `apikey`. Guárdala, la necesitas
   en el paso 3.

Nota: es una API gratuita pensada para uso personal, sin SLA formal. Para un
aviso a tu propio número está bien; si más adelante quieres avisar a varias
personas de forma garantizada, se cambia por Twilio WhatsApp API sin tocar el
resto del proyecto.

## 2. Crear el repositorio en GitHub

1. Crea un repo nuevo (puede ser privado) y sube estos archivos tal cual
   (`monitor.py`, `sites.json`, `state.json`, `requirements.txt`, la carpeta
   `.github/workflows/`).
2. `state.json` empieza vacío (`{}`) — el propio script lo va llenando solo,
   no lo edites a mano.

## 3. Añadir tus credenciales como secrets

En el repo: **Settings → Secrets and variables → Actions → New repository secret**

**Para un solo número**, crea dos secrets:

- `CALLMEBOT_PHONE` → tu número con código de país, sin el `+` (ej: `34612345678`)
- `CALLMEBOT_APIKEY` → la apikey que te dio CallMeBot en el paso 1

**Para varios números**, en vez de los dos anteriores crea un solo secret
llamado `CALLMEBOT_RECIPIENTS` con una lista JSON. Importante: cada número
tiene que activarse por su cuenta con CallMeBot (paso 1) — no se puede
reutilizar el apikey de una persona para otro teléfono.

```json
[
  { "phone": "34612345678", "apikey": "111111" },
  { "phone": "584241574102", "apikey": "222222" }
]
```

Si `CALLMEBOT_RECIPIENTS` existe, el script la usa y manda el aviso a todos
los números de la lista; si no existe, usa `CALLMEBOT_PHONE`/`CALLMEBOT_APIKEY`
como antes.

## 4. Revisar/editar sites.json

Ya viene con tus 4 dominios principales:

```json
[
  { "name": "Kawasaki Málaga", "url": "https://kawasakimalaga.com" },
  { "name": "Ducati Málaga", "url": "https://ducatimalaga.com" },
  { "name": "Málaga Moto Center", "url": "https://malagamotocenter.com" },
  { "name": "Pont Grup", "url": "https://pontgrup.com" }
]
```

Si quieres añadir subdominios u otras webs del grupo, agrega más objetos
`{ "name": "...", "url": "..." }` a la lista.

## 5. Activar el workflow y probarlo

1. Ve a la pestaña **Actions** de tu repo. Si GitHub pregunta, habilita los
   workflows.
2. Entra en "Uptime check" → **Run workflow** para lanzarlo manualmente una
   vez y comprobar que corre sin errores (revisa el log del paso "Revisar
   los sitios...").
3. Para forzar una prueba real de aviso: cambia momentáneamente una URL en
   `sites.json` por algo que no exista (ej. `https://kawasakimalaga.com/esto-no-existe-404`
   no sirve porque devuelve 404 pero el dominio responde — mejor prueba con
   una URL de un dominio que no exista, tipo `https://sitio-que-no-existe-12345.com`),
   corre el workflow manualmente, confirma que te llega el WhatsApp, y
   después revierte el cambio.
4. A partir de ahí queda corriendo solo cada 5 minutos.

## Cómo funciona por dentro

- Cada ejecución revisa todos los sitios de `sites.json`. Si uno no responde
  (error de red o código HTTP ≥ 400), reintenta hasta 3 veces con 5 segundos
  de espera antes de darlo por caído — para no avisar por un simple parpadeo.
- Compara el resultado con el último estado guardado en `state.json`.
  - Si pasó de arriba a caído → manda WhatsApp 🔴 y guarda la hora.
  - Si pasó de caído a arriba → manda WhatsApp 🟢 con cuánto tiempo estuvo caído.
  - Si no cambió nada → no manda nada (así no te satura el teléfono).
- Al final, si `state.json` cambió, el propio workflow lo commitea de vuelta
  al repo para que la próxima ejecución sepa el estado anterior.

## Limitaciones a tener en cuenta

- GitHub no garantiza el disparo exacto cada 5 minutos: en horas de mucha
  carga puede retrasarse 5-30 minutos. No es para algo que necesite aviso en
  segundos.
- Si el repo pasa 60 días sin ninguna actividad, GitHub desactiva el cron
  automáticamente (te avisa por email) y hay que reactivarlo a mano en la
  pestaña Actions.
- CallMeBot es gratuito para uso personal, sin garantía formal de entrega.
