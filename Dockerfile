FROM hub.rat.dev/mambaorg/micromamba:1.5.8-jammy

USER root
WORKDIR /app

COPY requirements-prod.txt /tmp/requirements-prod.txt

# 分层安装 GIS 依赖：每一层成功后都可被 Docker 缓存，避免一次失败后重新下载全部包。
RUN micromamba create -y --strict-channel-priority -n spatial-agent-gis \
        -c https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge \
        -c https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main \
        python=3.11 pip \
    && micromamba clean --all --yes

# 栅格核心依赖单独成层，包含 GDAL/PROJ/Rasterio 的大型二进制包。
RUN micromamba install -y --strict-channel-priority -n spatial-agent-gis \
        -c https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge \
        -c https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main \
        rasterio pyproj \
    && micromamba clean --all --yes

# 矢量依赖单独成层，GeoPandas/Fiona 等失败时不会使前两层失效。
RUN micromamba install -y --strict-channel-priority -n spatial-agent-gis \
        -c https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge \
        -c https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main \
        geopandas shapely pyogrio fiona \
    && micromamba clean --all --yes

RUN PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    micromamba run -n spatial-agent-gis pip install --no-cache-dir -r /tmp/requirements-prod.txt \
    && micromamba clean --all --yes

COPY . /app

ENV PATH=/opt/conda/envs/spatial-agent-gis/bin:/opt/conda/envs/spatial-agent-gis/Library/bin:$PATH \
    GDAL_DATA=/opt/conda/envs/spatial-agent-gis/Library/share/gdal \
    PROJ_LIB=/opt/conda/envs/spatial-agent-gis/Library/share/proj \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    SPATIAL_AGENT_DATASET_CONFIG=/app/config/datasets.container.example.json \
    SPATIAL_AGENT_DATASET_ROOT=/data \
    SPATIAL_AGENT_REQUIRE_GIS=1 \
    PYTHONUNBUFFERED=1

RUN mkdir -p /app/outputs/runs /app/outputs/geojson /data \
    && chown -R $MAMBA_USER:$MAMBA_USER /app /data

USER $MAMBA_USER
EXPOSE 8088
CMD ["uvicorn", "production_api:app", "--host", "0.0.0.0", "--port", "8088", "--workers", "2"]
