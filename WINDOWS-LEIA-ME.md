# LocalConvert · fork Windows do Open Tangerine

Este é um trabalho derivado real do Open Tangerine, não o projeto C#/WPF anterior.
Upstream: https://github.com/sintaxerrorpvtltd/Open-Tangerine
Fork: https://github.com/walmirramos/Open-Tangerine · branch `codex/windows-radial`.
Base: commit `53f1a75` (Desktop 0.2.2). Licença GPL-3.0-only; autores e
avisos originais preservados. Mudanças do fork: interface principal radial,
resolução por hover UIA/Shell, acionamento por toque em Shift, preferências,
ações de arquivo e validação das imagens antes de publicar.

Tangerine para macOS (https://tangerineformac.com/) é uma referência independente,
distribuída na App Store. Não é um produto da Apple. Este fork não é afiliado a
esse produto, à Apple ou ao autor upstream; usa nome e ícone próprios.

## Executar

Execute `Aplicativo/LocalConvert/LocalConvert.exe`. Mantenha toda a pasta
`_internal` ao lado do EXE. Não precisa instalar Python ou executar como
administrador. Não há janela principal nem console; procure o ícone laranja
com setas na bandeja. Configurações e Encerrar estão no menu do ícone.

Em uma pasta comum do Explorador, mantenha o ponteiro sobre um arquivo local e
pressione/solte Shift. O disco continua aberto sem manter a tecla pressionada.
Passe o mouse em uma fatia e clique. Escape ou clique fora fecha. Tab alterna
Converter/Ferramentas/Ações; setas escolhem e Enter executa. F2 ou botão direito
oferece uma lista nativa como alternativa ao desenho. O atalho secundário
Ctrl+Alt+Espaço é opcional e desligado inicialmente.

Regra do Shift: amostragem a cada 16 ms, pressão isolada entre 25 ms e 5 segundos,
sem outra tecla/modificador ou botão do mouse durante o gesto. Repetições não
abrem várias vezes; intervalo mínimo de 600 ms. Não há hooks globais ou bloqueio
de teclas. A amostragem pode perder combinações muito rápidas; não representa
garantia universal de detecção. Ativação pode ser desligada na bandeja.

O resolvedor usa UI Automation para o item no ponto e Shell.Application para o
caminho real. Nunca usa o último item selecionado nem concatena pasta com texto
visível. Se a resolução for ambígua, a pasta for virtual ou o ponteiro sair do
item durante a consulta, não abre conversões. A consulta tem limite de 8 s.

## Funcionalidades ligadas ao disco

- Imagens: PNG, JPEG, WebP (quando Pillow confirma encoder), TIFF, BMP e PDF de
  uma página. Entrada PNG/JPEG/WebP/TIFF/BMP/AVIF; conteúdo é decodificado antes
  de abrir as opções. Imagens animadas e múltiplas páginas são rejeitadas.
- Ferramentas: redimensionar proporcionalmente como PNG; girar 90° como PNG;
  compressão como JPEG com qualidade escolhida; gerar arquivo SHA-256.
- Ações: copiar caminho, copiar arquivo (Qt/Windows CF_HDROP), mostrar origem e
  fixar arquivo em pequena prateleira arrastável.
- PDF: extrair texto existente e dividir páginas. Não inclui OCR ou Word/Excel.
- Legendas: SRT/VTT simples, herdadas do upstream.

Imagens convertidas têm metadados auxiliares descartados, EXIF de orientação
aplicado e transparência achatada em branco para JPEG/BMP/PDF. Compressão não
garante arquivo menor em todo conteúdo. Originais e saídas existentes não são
substituídos; colisões recebem sufixos numéricos. O sufixo herdado é `-converted`.
O temporário é validado antes de ser publicado. Em FAT/exFAT a publicação
herdada pode usar cópia exclusiva em vez de operação atômica.

Áudio/vídeo existem no mecanismo upstream e seus testes; ainda não são
oferecidos no novo disco. FFmpeg não é empacotado, baixado ou executado pelo
disco. HEIC, conversão Office, Pages e recursos de IA não são anunciados.

## Preparar e compilar no Windows

Python 3.14 x64 foi usado neste notebook. O upstream recomenda 3.12; esta
derivação foi instalada/testada com 3.14 e as versões fixadas abaixo.

```powershell
git clone --branch codex/windows-radial https://github.com/walmirramos/Open-Tangerine.git
cd Open-Tangerine
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r Desktop/requirements.txt pyinstaller==6.22.3
.\.venv\Scripts\pythonw.exe Desktop/windows_main.py
```

Empacotar (Windows x64):

```powershell
.\.venv\Scripts\python.exe Desktop/package_windows.py
```

Saída: `Aplicativo/LocalConvert/LocalConvert.exe`. PyInstaller em modo windowed;
processos filhos têm pipes explícitos para o protocolo JSON, sem console.
O pacote contém o código correspondente e licenças. Não é assinado; não há
certificado disponível. Não é MSIX. Não altera o início automático do Windows.

## Testes reproduzíveis

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s Desktop/tests -v
.\.venv\Scripts\pythonw.exe Desktop/windows_main.py --quit
.\.venv\Scripts\python.exe Desktop/windows_main.py --self-test test-results
# Para testar o EXE publicado, com nenhuma outra instância rodando:
.\Aplicativo\LocalConvert\LocalConvert.exe --self-test test-results
```

O teste integrado abre uma pasta de fixtures no Explorador, seleciona A,
resolve B por UIA/Shell, mostra o overlay Qt real, despacha um clique no setor e
converte B pelo worker original. As amostras de Shift, coordenadas e clique Qt
são sintéticos. Não prova o gesto físico global nem multimonitor. Relatório
JSON e captura ficam na pasta escolhida, sem histórico permanente de uso.

Os testes usam somente arquivos gerados por eles. A versão normal não salva
teclas, caminhos de histórico, conteúdo ou telemetria. Preferências usam QSettings
no perfil do usuário. O código herdado continua disponível em `Desktop/app.py`
para compatibilidade/testes, mas o EXE usa `windows_main.py` e começa na bandeja.

## Dependências e licenças

Python 3.14 (PSF), Pillow 13.0.0 (HPND/MIT-CMU), pypdf 6.21.1 (BSD-3-Clause),
PySide6-Essentials/shiboken6 6.12.0 (LGPLv3/GPL/comercial), comtypes 1.4.17
(MIT), pywin32 312 (PSF), PyInstaller 6.22.3 (GPL com exceção do bootloader).
Qt é ligado dinamicamente. Consulte os textos distribuídos, `LICENSE`, `NOTICE`
e `THIRD_PARTY_NOTICES.md`; redistribuições do fork devem fornecer o código
correspondente e cumprir GPLv3 e as condições das bibliotecas.

## Limitações e próximas etapas

Escopo inicial: arquivos regulares locais em pastas comuns do Explorador.
Área de Trabalho, busca, pastas virtuais, nuvem/reparse points e outros
gerenciadores não estão homologados; links/reparse/UNC são recusados pelo núcleo.
Não há equivalência completa ao Tangerine macOS. Alto contraste e leitores de
tela precisam de auditoria; a alternativa F2 é um QMenu nativo acessível.
Monitores com DPI diferentes e acionamento físico devem ser verificados
separadamente. Prioridades seguintes: homologação física, cores de alto
contraste, FFmpeg por capacidades, progresso por arquivo e operações em lote
no mesmo disco. Recursos inexistentes não aparecem como botões funcionais.
