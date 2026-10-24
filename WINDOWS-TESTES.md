# Testes do fork Windows · 24/10/2026

Ambiente real: Windows x64, Python 3.14, Qt/PySide6 6.12.0. Dependências fixadas
em `Desktop/requirements.txt`. Não foi usado o EXE C#/WPF anterior.

## Suíte automatizada do código-fonte

Comando: `.venv/Scripts/python.exe -m unittest discover -s Desktop/tests -v`.

Resultado: **69 testes executados, 2 ignorados, nenhum erro/falha**.
Os dois testes ignorados verificam nomes com quebras de linha (proibidos pelo
Windows) e relato de sinais POSIX (específico de Unix). Os motivos completos constam no log de execução.
A suíte inclui os testes originais e oito testes novos do fork.

Cobertura relevante: PNG/JPEG/WebP/TIFF/BMP, orientação/alpha, PDF e legendas,
preservação do original, colisões, Unicode, cancelamento/timeouts do worker,
formatos compatíveis, setores arredondados, lacunas sem ação, Shift isolado,
repetição, debounce, combinações, despacho somente ao soltar, rejeição de nomes
Shell ambíguos e uso do caminho retornado pelo Shell. FFmpeg instalado no
ambiente foi exercitado pelos testes originais de mídia; não é oferecido no disco.

## Integração no Explorador real

Execução de fonte `execucao-dd4cad89`: **12 verificações aprovadas**.

1. Shift pressionado ainda não abre; soltura isolada aceita; combinação rejeita.
2. Pasta real de fixtures aberta com A selecionado e B não selecionado.
3. UI Automation + Shell identifica o caminho real de B no ponto consultado.
4. Overlay Qt mostrado e confirmado com `IsWindowVisible` do Windows.
5. Ponto do setor PNG acerta; centro não ativa conversão.
6. Clique Qt fecha o disco e despacha `Batch → runner → engine` do upstream.
7. Saída PNG decodificada com os pixels azuis de B, não os vermelhos de A.
8. SHA-256 de ambos os originais permanece igual.

O teste fornece coordenadas e eventos de entrada. **Não é comprovação de toque
físico global em Shift.** A consulta ao Shell, a seleção A/B, o overlay nativo,
o worker e os arquivos são reais. A primeira falha desse teste foi corrigida
configurando DPI por monitor também no subprocesso sem Qt; antes disso suas
coordenadas não estavam no mesmo espaço físico da interface.

## Limites da validação

A ferramenta de controle remoto retornou `FrameArrived timed out` ao capturar
o Explorador e `coordinate input geometry is unavailable` ao tentar clicar por
acessibilidade. Portanto, não foi possível completar por ela a sequência de
entrada global do Windows. Nenhuma nova tentativa manual foi exigida do usuário.

Permanecem sem homologação: teclado/mouse físicos, dois monitores com escalas
diferentes, alto contraste/leitor de tela, Área de Trabalho, busca, nuvem e
outros gerenciadores. Isso não é uma declaração de equivalência integral ao Mac.

Os resultados do executável portátil são registrados adicionalmente após sua
compilação; uma compilação bem-sucedida não é tratada como teste de interação.
