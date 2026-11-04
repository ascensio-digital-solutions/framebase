# Hair System Expert Agent

Domain-expert agent for Hair Solutions Co. Understands every technical aspect of men's
hair replacement systems — materials, construction, attachment, color, density, styling,
and how to reproduce the product in any scenario.

## Architecture

```
hair_system_expert/
├── agent.py              # Agent definition with RAG + Memory + tools
├── tools.py              # Product lookup, color matcher, density calculator
├── knowledge/            # Source documents for RAG Data Store
│   └── hair_system_bible.md   # Complete technical reference
├── tuning/               # Fine-tuning datasets
│   ├── sft_dataset.jsonl      # Supervised fine-tuning examples
│   └── preference_pairs.jsonl # DPO preference pairs
└── evaluation/           # Quality eval test cases
    └── test_questions.jsonl
```

## Knowledge layers

| Layer | Technology | Content |
|---|---|---|
| **Runtime truth** | Data Store RAG (GCS → Agent Studio) | Product specs, materials, color charts, attachment guides |
| **Cross-session memory** | Memory Bank | Client hair type, past systems ordered, preferences |
| **Baked expertise** | SFT + DPO fine-tuning | Domain fluency, brand voice, consultation flow |