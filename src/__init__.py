"""Heart Disease MLOps package.

Modules:
    data_loader   - load + split the processed dataset
    preprocessing - feature schema + sklearn ColumnTransformer pipeline
    train         - end-to-end training entrypoint (MLflow-instrumented)
    evaluate      - metrics and plot helpers
    api           - FastAPI inference service
"""

__version__ = "1.0.0"
