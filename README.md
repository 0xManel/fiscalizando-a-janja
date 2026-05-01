# Fiscalizando a JANJA e o PT

Dossiê público, direto e verificável sobre **Janja, governo Lula/PT, Presidência, cartão corporativo, sigilo, viagens oficiais e dívida pública**.

A ideia é simples: **o dinheiro é público, a conta também**. Se o governo usa estrutura, cartão, comitiva, sigilo ou discurso para empurrar a conta para o contribuinte, este projeto coloca número, fonte e ressalva na tela.

Site em produção:

https://fiscalizando-a-janja.vercel.app

Repositório público:

https://github.com/0xManel/fiscalizando-a-janja

## O que este projeto faz

- Baixa e processa bases públicas oficiais.
- Separa registros diretos ligados à Janja de contexto, equipe, comitiva e Presidência.
- Mostra gastos, cartões, sigilo e dívida em linguagem simples para qualquer pessoa entender.
- Expõe fontes e metodologia para conferência pública.
- Mantém rótulos de evidência para evitar manipulação:
  - **Direto:** registro oficial em nome de Rosângela/Janja.
  - **Contexto:** equipe, apoio, comitiva, agenda ou menção.
  - **Presidência/CPGF:** camada do governo federal; não é atribuição pessoal automática.
  - **Pista:** termo ou padrão que merece investigação, mas ainda não é prova direta.

## Correção anti-fake antes do lançamento

Este projeto **não** afirma que “Janja gastou R$ 7 bilhões em viagens”.

A leitura correta é:

- **R$ 7,43 bi**: todas as viagens federais oficiais no período monitorado, base ampla do Portal da Transparência.
- **R$ 7,48 bi sob lupa**: viagens federais oficiais + CPGF da Presidência + estrutura/equipe citada em fonte pública.
- **R$ 236,7 mil**: total direto conservador em registros oficiais ligados à Janja.
- **R$ 239,8 mil**: Janja + contexto/comitiva no recorte de viagens.

Qualquer valor de Presidência, equipe, CPGF, comitiva ou sigilo deve ficar separado do gasto pessoal direto.

## Princípios editoriais

- **Sem fonte, não vira acusação.**
- **Sem prova, não vira gasto pessoal.**
- **Sem transparência, não ganha passe livre.**
- Valores de comitiva, apoio e menções ficam separados do total direto.
- CPGF/Presidência é camada de contexto e cobrança pública, não atribuição automática à Janja.
- Reportagens entram como contexto/pista quando ajudam a explicar dados públicos; não substituem fonte primária.
- Não afirmamos crime, corrupção, desvio ou irregularidade como fato sem fonte jurídica/oficial robusta.

## Fontes principais

- Portal da Transparência — downloads oficiais de viagens.
- Portal da Transparência — CPGF / Cartão de Pagamento do Governo Federal.
- Banco Central — séries de dívida pública.
- Fontes jornalísticas confiáveis usadas como contexto, com ressalva explícita.

## Comandos locais

```bash
npm run scan      # roda scanners e regenera a base consolidada
npm run scan:db   # regenera apenas data/processed/dossier-db.json
npm run check     # valida arquivos, JSONs e tokens críticos da UI
npm run serve     # abre servidor local na porta 4173
```

## Estrutura

- `index.html` — página pública.
- `styles.css` — visual mobile-first, escuro, Brasil, cards diferenciados.
- `app.js` — renderização dos dados no navegador.
- `scripts/scan_radar_janja.py` — scanner de viagens oficiais.
- `scripts/scan_government_context.py` — scanner de contexto de governo, dívida e CPGF.
- `scripts/build_dossier_db.py` — consolida o dossiê em `data/processed/dossier-db.json`.
- `scripts/check_project.py` — checagem técnica antes de deploy.
- `data/processed/` — dados processados publicados no site.
- `data/raw/` — downloads brutos oficiais, ignorados no git/deploy.

## Deploy

O projeto é estático e roda na Vercel.

```bash
npm run check
vercel --prod --yes
```

## Aviso importante

Este painel é uma ferramenta de fiscalização cidadã baseada em registros públicos. Ele não é sentença judicial e não afirma crime por padrão. O objetivo é **expor a conta, separar camadas e facilitar cobrança pública com fonte aberta**.
