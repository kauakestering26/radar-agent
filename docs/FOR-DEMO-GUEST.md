# Radar Agent — Demo (guia pro convidado)

> Isso aqui é o que você manda pro dono (ou qualquer pessoa que vá rodar
> o agent numa máquina diferente da sua) antes da demo. Texto pronto pra
> copiar/colar no WhatsApp, email ou doc.

---

## Mensagem sugerida

> **Assunto**: Demo do Radar Agent — o que você precisa na sua máquina
>
> Oi [nome],
>
> Pra gente fazer a demo do Radar Agent, você roda um container pequeno
> no seu notebook e eu vejo os resultados no meu dashboard em tempo
> real. Credencial nunca sai do seu lado.
>
> **Você precisa ter:**
>
> 1. **Docker Desktop** instalado e rodando
>    Download: https://www.docker.com/products/docker-desktop/
>    (Windows, Mac e Linux — instala, reinicia, abre Docker Desktop e
>    espera o ícone ficar verde na bandeja)
>
> 2. Um terminal qualquer (PowerShell no Windows já vem)
>
> Só isso. Sem Python, sem Git, sem nada pra instalar.
>
> **Passo a passo no dia:**
>
> Vou te mandar na hora:
> - Um arquivo chamado `docker-compose.demo.yml`
> - Uma URL pro meu control-plane (tipo `wss://radar-dev.trycloudflare.com`)
>
> Você:
>
> 1. Salva o arquivo numa pasta qualquer
> 2. Edita UMA linha dele: trocar `CHANGE_ME` pela URL que eu te mandei
> 3. Abre o terminal naquela pasta e roda:
>
>    ```
>    docker compose -f docker-compose.demo.yml up -d
>    ```
>
> 4. Me avisa. Aí dou refresh no meu dashboard e seu notebook aparece
>    conectado. Em ~3 minutos a gente valida o fluxo inteiro.
>
> No fim da demo, pra limpar tudo:
>
> ```
> docker compose -f docker-compose.demo.yml down -v
> ```
>
> Isso remove o container e qualquer dado de teste. Zero resíduo na sua máquina.

---

## Checklist interno (pro dev, véspera da demo)

- [ ] Enviei o `docker-compose.demo.yml` pro convidado
- [ ] Enviei a URL do control-plane pro convidado (rede local ou Cloudflare tunnel)
- [ ] Convidado confirmou que o Docker Desktop está rodando na máquina dele
- [ ] Meu control-plane está de pé em `http://localhost:8000` com dashboard abrindo
- [ ] Testei a URL que mandei pra ele (do próprio celular ou outra máquina)
- [ ] `docs/DEMO.md` aberto no meu segundo monitor
- [ ] `tests/security/report.md` aberto pra mostrar o PASS
- [ ] `docs/PARITY.md` e `PITCH.md` abertos como apoio
