# OTEL Jev Log Signals

An open source OTLP/HTTP JSON relay that adds Jev decisions to OpenTelemetry logs grouped by a log template such as `log.record.template` from Drain. It keeps every log record and evaluates each distinct template once per process cache lifetime. The output adds `jev.log.outcome`, `jev.log.probability`, and `jev.log.policy_version` attributes. A decision below 0.90 confidence becomes `review`; a failed Jev or upstream request returns HTTP 503 so the sender can retry.

This is a relay, not a native OpenTelemetry Collector processor. It has not been tested against a live Collector or a live Jev account. The bounded in-memory cache is lost on restart; use the OTLP sender's normal retry policy and treat the downstream sink as the durable system of record. The relay listens on loopback only. Deploy an authenticated ingress if traffic must cross hosts.

## English

Run the offline sample:

```sh
python3 -m unittest discover -s tests -v
python3 relay.py --demo
```

To run the relay, set `TYPESAFE_API_KEY` and `OTLP_UPSTREAM_URL` in your private environment, then run `python3 relay.py --serve`. The upstream must be an HTTPS `/v1/logs` endpoint or a localhost HTTP `/v1/logs` endpoint. Point the OTLP/HTTP log exporter to `http://127.0.0.1:8091/v1/logs`. Use the Drain processor before this relay to supply `log.record.template`. Records without that attribute pass through unchanged. Existing `jev.log.*` output fields and malformed batches are rejected with HTTP 400. Never place an API key in an OTLP payload or commit it.

## Français

Exécutez l'exemple hors ligne avec `python3 -m unittest discover -s tests -v`, puis `python3 relay.py --demo`. Pour démarrer le relais, définissez `TYPESAFE_API_KEY` et `OTLP_UPSTREAM_URL` dans votre environnement privé, puis lancez `python3 relay.py --serve`. La destination doit être une URL HTTPS `/v1/logs` ou une URL HTTP locale `/v1/logs`. Configurez l'exportateur de logs OTLP/HTTP vers `http://127.0.0.1:8091/v1/logs`. Placez le processeur Drain en amont pour fournir `log.record.template`. Les logs sans cet attribut traversent le relais sans changement. Un lot mal formé ou contenant déjà les champs de sortie `jev.log.*` reçoit HTTP 400. Conservez la clé API hors du dépôt et des données OTLP.

Le relais conserve chaque log et ne classe qu'une fois chaque modèle distinct pendant la durée de vie du cache en mémoire. Une probabilité inférieure à 0,90 produit `review`. Un échec Jev ou de la destination renvoie HTTP 503 pour permettre une nouvelle tentative. Il s'agit d'un relais, pas d'un processeur natif du Collector. Aucun test avec un Collector ou un compte Jev réel n'a été effectué. Le cache disparaît au redémarrage ; utilisez la politique de nouvelle tentative de l'expéditeur et une destination durable. Le relais écoute uniquement en local ; ajoutez une entrée authentifiée pour un déploiement entre machines.

## Español

Ejecute el ejemplo sin conexión con `python3 -m unittest discover -s tests -v` y después `python3 relay.py --demo`. Para iniciar el repetidor, defina `TYPESAFE_API_KEY` y `OTLP_UPSTREAM_URL` en su entorno privado y ejecute `python3 relay.py --serve`. El destino debe ser una URL HTTPS `/v1/logs` o una URL HTTP local `/v1/logs`. Configure el exportador de registros OTLP/HTTP para `http://127.0.0.1:8091/v1/logs`. Coloque el procesador Drain antes del repetidor para proporcionar `log.record.template`. Los registros sin ese atributo pasan sin cambios. Un lote incorrecto o con campos de salida `jev.log.*` existentes recibe HTTP 400. Mantenga la clave API fuera del repositorio y de los datos OTLP.

El repetidor conserva todos los registros y evalúa una sola vez cada plantilla distinta durante la vida de la caché en memoria. Una probabilidad inferior a 0,90 produce `review`. Un fallo de Jev o del destino devuelve HTTP 503 para permitir un reintento. Es un repetidor, no un procesador nativo del Collector. No se ha probado con un Collector ni con una cuenta Jev reales. La caché se pierde al reiniciar; utilice la política de reintentos del emisor y un destino duradero. El repetidor escucha solo en la interfaz local; añada una entrada autenticada si el tráfico cruza entre máquinas.

License: MIT. Release: `v0.1.0`.
