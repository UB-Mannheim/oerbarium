# 🌳 OERbarium

CLI to collect, parse and map Open Educational Resources (OER) metadata into the
[DALIA Interchange Format (DIF V1.4)](https://doi.org/10.5281/zenodo.17871138) using Large Language Models.

## Contents

- [Installation](#installation)
- [LLM configuration](#llm-configuration)
- [CLI commands](#cli-commands)
  - [`oerbarium parse`](#oerbarium-parse)
  - [`oerbarium crawl dariah`](#oerbarium-crawl-dariah)
- [Acknowledgement](#acknowledgement)

## Installation

### Clone repository

```bash
git clone https://github.com/UB-Mannheim/oerbarium.git
```

### Change to project dir

```bash
cd oerbarium
```

### Install with `uv`

```bash
uv sync
```

## LLM Configuration

> The LLM configuration expects an OpenAI compatible endpoint. **Only models with tool calling capabilities are supported.**

Set these via environment variables or a `config.env` file in the working
directory:

```env
API_KEY=your-api-key
API_BASE_URL=https://llmservice.example.org/v1
MODEL_NAME=qwen3.8-27b-thinking
```

## CLI commands

The CLI is installed as `oerbarium`.

```bash
oerbarium --help

Usage: oerbarium [OPTIONS] COMMAND [ARGS]...

  🌳 Collect, parse and map Open Educational Resources (OER) metadata into the
  DALIA Interchange Format (DIF V1.4).

Options:
  --help  Show this message and exit.

Commands:
  crawl  Collect raw OER metadata from a source site.
  parse  Parse messy OER metadata into DIF V1.4.
```

### `oerbarium parse`

Parse OER metadata into DIF V1.4 using an LLM.

The more metadata or descriptive content provided for an OER, the more accurately the LLM can map the resource to DIF V1.4.

#### Example usage

```bash
oerbarium parse -i crawled.json -o parsed.json
```

| Option | Description |
| --- | --- |
| `-i, --input` | Input file: `.txt` (one OER per file) or `.json` (one OER per list item) (required) |
| `-o, --output-path` | Output path; rewritten after every parsed record (required) |
| `-f, --format` | Output format: `json` (default) or `tsv` |
| `-m, --model-name` | LLM model name (overrides `MODEL_NAME`) |
| `-b, --base-url` | API base URL (overrides `API_BASE_URL`) |
| `--api-key` | API key (overrides `API_KEY`) |
| `--strict` | Abort on the first failing record; already-parsed records are kept |
| `-v, --verbose` | Log progress and tool calls |

Records parsed before a failure remain in the output file even without
`--strict`.

#### How to provide OER metadata

`-i, --input` is required to run the LLM parsing and expects one of two file types:

##### Option 1: `.txt` with raw OER metadata

Raw metadata (e.g. copied & pasted from an OER repository) saved as one individual `.txt` like in this example from [OER Commons](https://oercommons.org/courses/critical-data-literacy):

```txt
Critical Data Literacy
0.0 stars
Description

Overview:
    Strategies to Effectively Interpret and Evaluate Data Visualizations

    Short Description:
    A short course for students to increase their proficiency in analyzing and interpreting data visualizations. By completing this short course students will be able to explain the importance of data literacy, identify data visualization issues in order to improve their own skills in data story-telling. The intended outcome of this course is to help students become more discerning and critical users of data, graphs, charts and infographics.


    Word Count: 9819

    (Note: This resource's metadata has been created automatically by reformatting and/or combining the information that the author initially provided as part of a bulk import process.)

Subject:
    Computer Science 
Level:
    Community College / Lower Division 
Material Type:
    Textbook 
Provider:
    Toronto Metropolitan University 
Date Added:
    02/28/2022

License:
    Creative Commons Attribution Creative Commons Attribution 
Language:
    English 
Media Format:
    Text/HTML 

Comments
Standards

No Alignments yet.
Evaluations

No evaluations yet.
Tags (4)
    Disinformation and Misinformation Information Visualization PB 1 2024 Pressbooks 
```

##### Option 2: `.json` array

Metadata exported from an OER repository as `.json`. The individual json structure might differ from repository to repository and is not relevant for processing.

See this example that captures two individual [OERSI](https://oersi.org/) records into one `.json` array.

```json
[
   {"image":"https://www.zoerr.de/edu-sharing/preview?nodeId=34ba77cf-a033-48f6-ba77-cfa03308f61d&storeProtocol=workspace&storeId=SpacesStore&dontcache=1787097049658","creator":[{"name":"Team MaDaLi²","type":"Person"}],"keywords":["MaDaLi²","H5P","Datenkompetenz (Data Literacy)","Daten (Daten)","Forschungsdaten (Research Data)"],"about":[{"prefLabel":{"cs":"Mezioborový","de":"Fachübergreifend","sv":"Tvärvetenskapligt","uk":"Міждисциплінарний","el":"Διεπιστημονικό","sk":"Interdisciplinárny","en":"Interdisciplinary","it":"Interdisciplinare","fr":"Interdisciplinaire","es":"Interdisciplinario"},"id":"https://w3id.org/kim/hochschulfaechersystematik/n0"}],"description":"Das erste Modul des E-Learning-Kurses Mannheim Data Literacy (MaDaLi²) vermittelt eine grundlegende Einführung in zentrale Konzepte der Data Literacy. Behandelt werden die Definition und Alltagsrelevanz von Daten, der verantwortungsbewusste Umgang mit Daten sowie der Forschungsdatenlebenszyklus. Zudem werden grundlegende Ansätze der Datenauswertung vorgestellt. Die Einheit arbeitet mit authentischen Datensätzen und bereitet inhaltlich auf die vertiefenden Module des Kurses vor.\n\nDisclaimer: Dieses Modul wird unter einer CC BY-SA-Lizenz zur Verfügung gestellt. Sofern nicht anders angegeben, stehen auch die einzelnen Inhalte unter einer CC BY-SA-Lizenz. Eine Übersicht der einzelnen Lizenzen findet sich im Metadaten-Abschnitt \"Beziehungen & Versionen\".","inLanguage":["de"],"dateModified":"2026-01-28","isAccessibleForFree":true,"type":["LearningResource"],"mainEntityOfPage":[{"dateCreated":"2026-01-28","provider":{"name":"ZOERR","id":"https://www.zoerr.de","type":"Service"},"dateModified":"2026-01-28","id":"https://www.zoerr.de/edu-sharing/components/render/34ba77cf-a033-48f6-ba77-cfa03308f61d","type":"WebContent"}],"encoding":[{"contentUrl":"https://www.zoerr.de/edu-sharing/eduservlet/download?nodeId=34ba77cf-a033-48f6-ba77-cfa03308f61d","contentSize":"138285749","encodingFormat":"application/zip","type":"MediaObject"},{"embedUrl":"https://www.zoerr.de/edu-sharing/eduservlet/render?node_id=34ba77cf-a033-48f6-ba77-cfa03308f61d","type":"MediaObject"}],"@context":["https://w3id.org/kim/amb/context.jsonld",{"@language":"de"}],"conditionsOfAccess":{"prefLabel":{"cs":"přihlášení není vyžadováno","de":"keine Anmeldung erforderlich","uk":"вхід без авторизації","en":"no login required","nl":"geen login vereist"},"id":"http://w3id.org/kim/conditionsOfAccess/no_login"},"license":{"id":"https://creativecommons.org/licenses/by-sa/4.0/"},"dateCreated":"2026-01-28","name":"MaDaLi² – Module 1: Daten verstehen","sourceOrganization":[{"name":"Universität Mannheim","location":[{"address":{"addressCountry":"DE","addressLocality":"Mannheim","addressRegion":"Baden-Wurttemberg"}}],"id":"https://ror.org/031bsb921","type":"Organization"}],"id":"https://www.zoerr.de/edu-sharing/components/render/34ba77cf-a033-48f6-ba77-cfa03308f61d","learningResourceType":[{"prefLabel":{"de":"Kurs","sv":"Kurs","fi":"Kurssi","el":"Μάθημα","en":"Course","it":"Corso","fr":"Cours","es":"Curso","cs":"Kurz","uk":"Курс","sk":"Kurz","da":"Kursus","nl":"Cursus"},"id":"https://w3id.org/kim/hcrt/course"}]},
   {"image":"https://www.zoerr.de/edu-sharing/preview?nodeId=ec3d6e8e-7f71-4a56-bd6e-8e7f719a562d&storeProtocol=workspace&storeId=SpacesStore&dontcache=1787097056055","creator":[{"name":"Team MaDaLi²","type":"Person"}],"keywords":["MaDaLi²","H5P","Offene Lizenzen","CC Lizenzen","Datenkompetenz (Data Literacy)","Urheberrecht (Copyright, Urheberschutz)","E-Learning (Learning on demand, Digitales Lernen)","Datenschutz (Datenschutzrecht, Datenverarbeitung)","Forschungsdaten (Research Data)"],"about":[{"prefLabel":{"cs":"Mezioborový","de":"Fachübergreifend","sv":"Tvärvetenskapligt","uk":"Міждисциплінарний","el":"Διεπιστημονικό","sk":"Interdisciplinárny","en":"Interdisciplinary","it":"Interdisciplinare","fr":"Interdisciplinaire","es":"Interdisciplinario"},"id":"https://w3id.org/kim/hochschulfaechersystematik/n0"}],"description":"Das zweite Modul des E-Learning-Kurses Mannheim Data Literacy (MaDaLi²) führt in zentrale rechtliche, ethische und sicherheitsrelevante Aspekte des verantwortungsvollen Umgangs mit Daten ein. Im Mittelpunkt stehen Datenschutzgrundsätze und einschlägige gesetzliche Rahmenbedingungen in Deutschland und der EU, die Unterscheidung zwischen personenbezogenen und besonderen Kategorien personenbezogener Daten sowie urheber- und lizenzrechtliche Fragen. Ergänzend werden Grundlagen der Datensicherheit behandelt. Ein optionaler Exkurs bietet vertiefende Informationen zur informierten Einwilligung, die insbesondere für empirische Datenerhebungen Relevanz besitzt.\n\nDisclaimer: Dieses Modul wird unter einer CC BY-SA-Lizenz zur Verfügung gestellt. Sofern nicht anders angegeben, stehen auch die einzelnen Inhalte unter einer CC BY-SA-Lizenz. Eine Übersicht der einzelnen Lizenzen findet sich im Metadaten-Abschnitt \"Beziehungen & Versionen\".","inLanguage":["de"],"dateModified":"2026-01-26","isAccessibleForFree":true,"type":["LearningResource"],"mainEntityOfPage":[{"dateCreated":"2026-01-26","provider":{"name":"ZOERR","id":"https://www.zoerr.de","type":"Service"},"dateModified":"2026-01-26","id":"https://www.zoerr.de/edu-sharing/components/render/ec3d6e8e-7f71-4a56-bd6e-8e7f719a562d","type":"WebContent"}],"encoding":[{"contentUrl":"https://www.zoerr.de/edu-sharing/eduservlet/download?nodeId=ec3d6e8e-7f71-4a56-bd6e-8e7f719a562d","contentSize":"540236089","encodingFormat":"application/zip","type":"MediaObject"},{"embedUrl":"https://www.zoerr.de/edu-sharing/eduservlet/render?node_id=ec3d6e8e-7f71-4a56-bd6e-8e7f719a562d","type":"MediaObject"}],"@context":["https://w3id.org/kim/amb/context.jsonld",{"@language":"de"}],"conditionsOfAccess":{"prefLabel":{"cs":"přihlášení není vyžadováno","de":"keine Anmeldung erforderlich","uk":"вхід без авторизації","en":"no login required","nl":"geen login vereist"},"id":"http://w3id.org/kim/conditionsOfAccess/no_login"},"license":{"id":"https://creativecommons.org/licenses/by-sa/4.0/"},"dateCreated":"2026-01-26","name":"MaDaLi² – Modul 2: Datenethik beachten","sourceOrganization":[{"name":"Universität Mannheim","location":[{"address":{"addressCountry":"DE","addressLocality":"Mannheim","addressRegion":"Baden-Wurttemberg"}}],"id":"https://ror.org/031bsb921","type":"Organization"}],"id":"https://www.zoerr.de/edu-sharing/components/render/ec3d6e8e-7f71-4a56-bd6e-8e7f719a562d","learningResourceType":[{"prefLabel":{"de":"Kurs","sv":"Kurs","fi":"Kurssi","el":"Μάθημα","en":"Course","it":"Corso","fr":"Cours","es":"Curso","cs":"Kurz","uk":"Курс","sk":"Kurz","da":"Kursus","nl":"Cursus"},"id":"https://w3id.org/kim/hcrt/course"}]}
]

```

### `oerbarium crawl dariah`

Crawl DARIAH Campus resource pages into a JSON array of raw metadata.

```bash
oerbarium crawl dariah -i urls.txt -o crawled.json
```

| Option | Description |
| --- | --- |
| `-i, --input` | Path to a `.txt` file with one URL per line (required) |
| `-o, --output-path` | Path to write crawled metadata as a JSON array (required) |
| `--strict` | Abort on the first failing URL instead of skipping it |
| `-v, --verbose` | Log progress and skipped URLs |

## Acknowledgement

Claude Sonnet 5 and Opus 5 helped to create this app.
