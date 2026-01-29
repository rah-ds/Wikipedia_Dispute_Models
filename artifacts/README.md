# Artifacts Directory

Store model outputs, experimental results, and execution logs. These are meant to be experimental.

## Structure

```text
artifacts/
├── models/
│   ├── configs/       # Model configuration files
│   └── checkpoints/   # Saved model weights
├── imgs/
│   ├── dev/           # Development/exploratory figures
│   └── publish/       # Publication-ready figures
├── logs/
│   ├── build/         # Build and setup logs
│   └── training/      # Training run logs
├── results/           # Experiment outputs and metrics
└── exports/           # Exported data for sharing
```

## Guidelines

- **models/**: Store trained model artifacts; use descriptive names with dates
- **imgs/dev/**: Quick plots for exploration; can be messy
- **imgs/publish/**: Final figures for papers/presentations; high resolution
- **logs/**: Timestamped logs; rotate old logs periodically
- **results/**: JSON/CSV outputs from experiments, these are meant to be shared
