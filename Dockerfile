FROM mambaorg/micromamba:1.5.8-jammy

USER root
WORKDIR /app

COPY environment.yml /tmp/environment.yml
COPY requirements-prod.txt /tmp/requirements-prod.txt
RUN micromamba create -y -f /tmp/environment.yml \
    && micromamba run -n spatial-agent-gis pip install -r /tmp/requirements-prod.txt \
    && micromamba clean --all --yes

COPY . /app

ENV PATH=/opt/conda/envs/spatial-agent-gis/bin:/opt/conda/envs/spatial-agent-gis/Library/bin:$PATH \
    GDAL_DATA=/opt/conda/envs/spatial-agent-gis/Library/share/gdal \
    PROJ_LIB=/opt/conda/envs/spatial-agent-gis/Library/share/proj \
    SPATIAL_AGENT_DATASET_CONFIG=/app/config/datasets.container.example.json \
    SPATIAL_AGENT_DATASET_ROOT=/data \
    SPATIAL_AGENT_REQUIRE_GIS=1 \
    PYTHONUNBUFFERED=1

RUN mkdir -p /app/outputs/runs /app/outputs/geojson /data \
    && chown -R $MAMBA_USER:$MAMBA_USER /app /data

USER $MAMBA_USER
EXPOSE 8088
CMD ["uvicorn", "production_api:app", "--host", "0.0.0.0", "--port", "8088", "--workers", "2"]
