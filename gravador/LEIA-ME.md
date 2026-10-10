# HIPO Gravador

Grava as ligações do **Vivo Voz Negócio** feitas no computador e as manda para o HIPO, que transcreve, resume e coloca cada ligação na oportunidade.

## Instalar (por pessoa, em cada computador)

1. No HIPO, abra **Perfil → Gravador de ligações**, dê um nome ao computador e clique em **Gerar token**. Copie o token: ele só aparece uma vez.
2. Baixe o instalador pelo link da mesma tela e extraia o zip.
3. Clique com o botão direito em `instalar.ps1` e escolha **Executar com o PowerShell**. Não precisa ser administrador.
4. Cole o token quando o instalador pedir.

No fim, aparece um ícone **verde** perto do relógio. O instalador também deixa o gravador abrindo sozinho a cada logon.

## O ícone

| Cor | Significado |
|---|---|
| verde | pronto, aguardando ligação |
| vermelho | **gravando** a ligação |
| cinza | pausado (clique direito → Pausar gravação, para uma ligação pessoal) |
| amarelo | problema (token recusado, sem conexão com o HIPO) |

## Como funciona

- O gravador percebe a chamada pelo áudio do softphone: quando o Vivo Voz Negócio abre o **microfone**, a gravação começa. Quando o microfone fica 4 segundos sem uso, a gravação termina.
- Ele grava em **dois canais**: o microfone (quem ligou) e o som que o computador toca (o cliente). Por isso a transcrição separa os dois lados.
- O áudio sai do **dispositivo de comunicação** do Windows, que normalmente é o headset. Música tocando no mesmo fone durante a ligação também entra na gravação.
- Antes de ir para o HIPO, a gravação fica em `%LOCALAPPDATA%\HIPO Gravador\fila`. Sem internet, ela espera ali e é enviada quando a conexão voltar, por até 7 dias.
- Para a gravação já cair na oportunidade certa, **ligue clicando no telefone do contato dentro do HIPO**. Se discar direto no softphone, a ligação entra como "sem vínculo" na tela de Tarefas, e você escolhe de qual oportunidade ela é.

## Problemas

O diário fica em `%LOCALAPPDATA%\HIPO Gravador\gravador.log`. Para abrir, use o clique direito no ícone → **Abrir pasta do diário**.

Para conferir o token, o microfone, a saída de áudio e o softphone, rode na pasta `%LOCALAPPDATA%\HIPO Gravador\programa`:

```
..\venv\Scripts\python.exe hipo_gravador.pyw --testar
```

**O gravador não percebe a ligação.** O nome do processo do softphone pode não estar na lista. Rode o comando abaixo e faça uma ligação de teste enquanto ele roda:

```
..\venv\Scripts\python.exe hipo_gravador.pyw --descobrir 60
```

Ele lista os programas que usaram o microfone durante a ligação. Acrescente um trecho do nome do softphone em `"processos"` no arquivo `%APPDATA%\HIPO Gravador\config.json` e reinicie o gravador: clique direito no ícone → Sair, e depois rode no PowerShell `Start-ScheduledTask "HIPO Gravador"` (ou faça logoff e logon).

**Outros ajustes** em `config.json`:

- `"entrada"` e `"saida"`: o valor `"comunicacao"` (padrão) usa o dispositivo de comunicação do Windows, `"padrao"` usa o dispositivo padrão comum, e um trecho do nome escolhe um dispositivo específico (ex.: `"Jabra"`).
- `"detectar_por"`: use `"saida"` se o softphone deixar o microfone aberto o tempo todo.

## Desinstalar

Rode `desinstalar.ps1` e revogue o token em **Perfil → Gravador de ligações**.
