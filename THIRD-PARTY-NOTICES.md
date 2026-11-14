# Third-party notices

This project is released under the [MIT License](LICENSE). It uses the following third-party software, each under its own
license. Nothing from these projects is copied into this repository; they are installed by `pip` / `npm` or pulled as Docker images.

## Frontend (npm, see `frontend/package.json`)

| Package | License |
|---|---|
| React, React DOM | MIT |
| Three.js | MIT |
| Vite, @vitejs/plugin-react (build only) | MIT |

## Backend (pip, see `backend/requirements.txt`)

| Package | License |
|---|---|
| FastAPI, Starlette, Pydantic | MIT |
| Uvicorn | BSD-3-Clause |
| HTTPX | BSD-3-Clause |
| Netmiko | MIT |
| Paramiko | LGPL-2.1 |
| ntc-templates | Apache-2.0 |
| Jinja2 | BSD-3-Clause |
| PyYAML | MIT |
| confluent-kafka | Apache-2.0 |
| pytest (tests only) | MIT |

## Container images and monitoring stack

nginx, Python, Node, Apache Kafka, Kafka UI, Prometheus and Grafana images are used as published by their projects, under their
own licenses (BSD-2-Clause, PSF, MIT, Apache-2.0, Apache-2.0, Apache-2.0 and AGPL-3.0 respectively).

## Cisco IOS

Cisco IOS images are **not** included and are not distributed by this project. To run the real lab you need your own licensed
c7200 image for EVE-NG. Cisco and Cisco IOS are trademarks of Cisco Systems, Inc.; this project is not affiliated with or endorsed
by Cisco. Simulation mode models IOS behaviour and output for education and testing; it contains no Cisco code.
