"""
Preprocesamiento Landsat 8/9 — Cartagena de Indias
===================================================
Paso 1: Calcula LST y NDVI desde bandas crudas de Landsat Collection 2 Level-2.
Paso 2: Carga shapefile oficial de localidades (IGAC / datos.gov.co).

Uso:
    python preprocesamiento_landsat.py \\
        --carpeta_landsat /ruta/escena_landsat/ \\
        --shapefile_localidades /ruta/localidades_cartagena.shp \\
        --salida calor_cartagena/salida/rasters/

    # Sin shapefile oficial usa límites aproximados internos:
    python preprocesamiento_landsat.py \\
        --carpeta_landsat /ruta/escena_landsat/

Estructura esperada de la carpeta Landsat (Collection 2 Level-2):
    LC09_L2SP_008053_20240115_*_B4.TIF   (Rojo — SR)
    LC09_L2SP_008053_20240115_*_B5.TIF   (NIR  — SR)
    LC09_L2SP_008053_20240115_*_B10.TIF  (Térmica TIRS Band 10)
    LC09_L2SP_008053_20240115_*_MTL.txt  (Metadatos — opcional para QA)
"""

import os
import sys
import glob
import argparse
import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.mask import mask as rasterio_mask
import geopandas as gpd
import warnings

warnings.filterwarnings("ignore")

CRS_GEO  = "EPSG:4326"
CRS_PROJ = "EPSG:9377"   # MAGNA-SIRGAS / Colombia Oeste

SALIDA_DEFAULT = "calor_cartagena/salida/rasters"


# ──────────────────────────────────────────────────────────
# PASO 1A — LST desde banda B10 (Landsat Collection 2 L2)
# ──────────────────────────────────────────────────────────

def calcular_lst(ruta_b10: str, ruta_salida: str) -> str:
    """
    Convierte Band 10 (TIRS) a temperatura superficial en °C.

    Fórmula USGS Collection 2 Level-2:
        T_kelvin = B10 * 0.00341802 + 149.0
        T_celsius = T_kelvin - 273.15

    Valores DN = 0 o 65535 son nodata.
    """
    print(f"  Leyendo B10: {os.path.basename(ruta_b10)}")
    with rasterio.open(ruta_b10) as src:
        b10  = src.read(1).astype("float32")
        meta = src.meta.copy()
        nd   = src.nodata

    # Máscara nodata
    mascara = (b10 == 0) | (b10 == 65535)
    if nd is not None:
        mascara |= (b10 == nd)

    # Conversión a °C
    lst = b10 * 0.00341802 + 149.0 - 273.15
    lst[mascara] = np.nan

    # Rango físico esperado: 10–65 °C (trópico urbano)
    lst = np.where((lst < 10) | (lst > 70), np.nan, lst)

    stats = (np.nanmin(lst), np.nanmax(lst), np.nanmean(lst))
    print(f"  LST calculada — min: {stats[0]:.1f}°C  max: {stats[1]:.1f}°C  media: {stats[2]:.1f}°C")

    meta.update(dtype="float32", nodata=np.nan, count=1, compress="lzw")
    with rasterio.open(ruta_salida, "w", **meta) as dst:
        dst.write(lst, 1)
        dst.update_tags(
            descripcion="LST Landsat Collection 2 L2 en °C",
            formula="B10 * 0.00341802 + 149.0 - 273.15",
        )

    print(f"  Guardado: {ruta_salida}")
    return ruta_salida


# ──────────────────────────────────────────────────────────
# PASO 1B — NDVI desde bandas B4 (Rojo) y B5 (NIR)
# ──────────────────────────────────────────────────────────

def calcular_ndvi(ruta_b4: str, ruta_b5: str, ruta_salida: str) -> str:
    """
    Calcula NDVI desde reflectancia superficial (SR) de Landsat C2 L2.

    Escala SR (USGS):
        reflectancia = DN * 0.0000275 + (-0.2)

    NDVI = (NIR - Rojo) / (NIR + Rojo)
    Rango válido: -1 a 1
      < 0.1  → agua / suelo desnudo / asfalto
      0.1–0.3 → vegetación escasa
      > 0.3  → vegetación moderada a densa
      > 0.6  → manglar / bosque denso
    """
    print(f"  Leyendo B4 (Rojo): {os.path.basename(ruta_b4)}")
    print(f"  Leyendo B5 (NIR) : {os.path.basename(ruta_b5)}")

    with rasterio.open(ruta_b4) as src:
        b4   = src.read(1).astype("float32")
        meta = src.meta.copy()
        nd4  = src.nodata

    with rasterio.open(ruta_b5) as src:
        b5  = src.read(1).astype("float32")
        nd5 = src.nodata

    # Máscara nodata
    mask_nd = (b4 == 0) | (b5 == 0) | (b4 == 65535) | (b5 == 65535)
    if nd4 is not None:
        mask_nd |= (b4 == nd4)
    if nd5 is not None:
        mask_nd |= (b5 == nd5)

    # Aplicar factor de escala SR (Collection 2 Level-2)
    b4_sr = b4 * 0.0000275 + (-0.2)
    b5_sr = b5 * 0.0000275 + (-0.2)

    # Reflectancias físicamente válidas: 0–1
    mask_nd |= (b4_sr < 0) | (b4_sr > 1) | (b5_sr < 0) | (b5_sr > 1)

    # NDVI
    denominador = b5_sr + b4_sr
    denominador[denominador == 0] = np.nan
    ndvi = (b5_sr - b4_sr) / denominador
    ndvi[mask_nd] = np.nan
    ndvi = np.clip(ndvi, -1.0, 1.0)

    stats = (np.nanmin(ndvi), np.nanmax(ndvi), np.nanmean(ndvi))
    print(f"  NDVI calculado   — min: {stats[0]:.3f}  max: {stats[1]:.3f}  media: {stats[2]:.3f}")

    meta.update(dtype="float32", nodata=np.nan, count=1, compress="lzw")
    with rasterio.open(ruta_salida, "w", **meta) as dst:
        dst.write(ndvi, 1)
        dst.update_tags(
            descripcion="NDVI Landsat Collection 2 L2",
            formula="(B5_SR - B4_SR) / (B5_SR + B4_SR)",
            escala_sr="DN * 0.0000275 + (-0.2)",
        )

    print(f"  Guardado: {ruta_salida}")
    return ruta_salida


# ──────────────────────────────────────────────────────────
# PASO 1C — Reproyectar a WGS84 si el raster está en UTM
# ──────────────────────────────────────────────────────────

def reproyectar_a_wgs84(ruta_entrada: str, ruta_salida: str) -> str:
    """Reproyecta cualquier GeoTIFF a EPSG:4326 si no lo está ya."""
    with rasterio.open(ruta_entrada) as src:
        if str(src.crs) == CRS_GEO:
            print(f"  Ya en WGS84: {os.path.basename(ruta_entrada)}")
            return ruta_entrada

        transform, width, height = calculate_default_transform(
            src.crs, CRS_GEO, src.width, src.height, *src.bounds
        )
        meta = src.meta.copy()
        meta.update(crs=CRS_GEO, transform=transform,
                    width=width, height=height, compress="lzw")

        with rasterio.open(ruta_salida, "w", **meta) as dst:
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=CRS_GEO,
                    resampling=Resampling.bilinear,
                )

    print(f"  Reproyectado a WGS84: {ruta_salida}")
    return ruta_salida


# ──────────────────────────────────────────────────────────
# PASO 2 — Cargar shapefile oficial de localidades
# ──────────────────────────────────────────────────────────

def cargar_localidades_oficial(ruta_shp: str) -> gpd.GeoDataFrame:
    """
    Carga el shapefile oficial de localidades de Cartagena (IGAC / datos.gov.co).

    El shapefile puede tener distintos nombres de columna según la fuente.
    Esta función intenta detectar automáticamente la columna de nombre.

    Columnas mínimas esperadas en el shapefile IGAC:
        NOMBRE / nombre / NOM_LOC / LOCALIDAD  → nombre de la localidad
        CODIGO / COD_LOC / codigo              → código
    """
    print(f"\n  Cargando shapefile: {ruta_shp}")
    gdf = gpd.read_file(ruta_shp)

    # Normalizar nombres de columna a minúsculas
    gdf.columns = [c.strip().lower() for c in gdf.columns]
    print(f"  Columnas encontradas: {list(gdf.columns)}")
    print(f"  Registros: {len(gdf)}  |  CRS: {gdf.crs}")

    # Detectar columna de nombre
    candidatos_nombre = ["nombre", "nom_loc", "localidad", "name",
                         "nom_depto", "nombre_loc", "loc_nombre"]
    col_nombre = next((c for c in candidatos_nombre if c in gdf.columns), None)

    # Detectar columna de código
    candidatos_codigo = ["codigo", "cod_loc", "codigo_loc", "cod", "code", "objectid"]
    col_codigo = next((c for c in candidatos_codigo if c in gdf.columns), None)

    if col_nombre is None:
        print("  ADVERTENCIA: No se encontró columna de nombre. "
              "Usando índice como nombre.")
        gdf["nombre"] = ["Localidad_" + str(i+1) for i in range(len(gdf))]
        col_nombre = "nombre"

    # Estandarizar columnas requeridas
    gdf = gdf.rename(columns={col_nombre: "nombre"})
    if col_codigo and col_codigo != "codigo":
        gdf = gdf.rename(columns={col_codigo: "codigo"})
    elif "codigo" not in gdf.columns:
        gdf["codigo"] = ["L" + str(i+1) for i in range(len(gdf))]

    # Filtrar solo Cartagena si el shapefile es nacional
    if len(gdf) > 10:
        filtros = gdf["nombre"].str.contains(
            "cartagena|hist|virgen|industrial|bahía|caribe",
            case=False, na=False
        )
        gdf_ctg = gdf[filtros].copy()
        if len(gdf_ctg) > 0:
            print(f"  Filtradas {len(gdf_ctg)} localidades de Cartagena")
            gdf = gdf_ctg
        else:
            print("  No se encontraron localidades de Cartagena por nombre. "
                  "Usando todas las geometrías del shapefile.")

    gdf = gdf.to_crs(CRS_GEO)
    print(f"  Localidades cargadas:")
    for _, row in gdf.iterrows():
        print(f"    - {row['nombre']}  ({row['codigo']})")

    return gdf[["nombre", "codigo", "geometry"]]


def localidades_aproximadas() -> gpd.GeoDataFrame:
    """Retorna los polígonos aproximados internos si no hay shapefile oficial."""
    from modelacion_zonas_calor import crear_localidades_cartagena
    gdf = crear_localidades_cartagena()
    gdf = gdf.rename(columns={"id": "codigo"})[["nombre", "codigo", "geometry"]]
    print("  Usando límites aproximados internos (sin shapefile oficial).")
    return gdf


# ──────────────────────────────────────────────────────────
# DETECTOR AUTOMÁTICO DE BANDAS EN LA CARPETA LANDSAT
# ──────────────────────────────────────────────────────────

def detectar_bandas(carpeta: str) -> dict:
    """
    Busca automáticamente los archivos de banda dentro de la carpeta Landsat.
    Soporta Landsat 8 (LC08) y Landsat 9 (LC09), Collection 2.
    """
    patrones = {
        "B4":  ["*_B4.TIF", "*_SR_B4.TIF", "*_B4.tif"],
        "B5":  ["*_B5.TIF", "*_SR_B5.TIF", "*_B5.tif"],
        "B10": ["*_B10.TIF", "*_ST_B10.TIF", "*_B10.tif"],
        "MTL": ["*_MTL.txt", "*MTL.txt"],
    }

    encontradas = {}
    for banda, pats in patrones.items():
        for pat in pats:
            matches = glob.glob(os.path.join(carpeta, pat))
            if matches:
                encontradas[banda] = matches[0]
                break

    print(f"\n  Bandas detectadas en {carpeta}:")
    for banda, ruta in encontradas.items():
        print(f"    {banda}: {os.path.basename(ruta)}")

    for req in ["B4", "B5", "B10"]:
        if req not in encontradas:
            raise FileNotFoundError(
                f"No se encontró la banda {req} en {carpeta}. "
                f"Verifica que los archivos tengan el formato "
                f"LC08/LC09_L2SP_*_{req}.TIF"
            )

    return encontradas


# ──────────────────────────────────────────────────────────
# PIPELINE COMPLETO DE PREPROCESAMIENTO
# ──────────────────────────────────────────────────────────

def ejecutar_preprocesamiento(carpeta_landsat: str,
                               shapefile_localidades: str = None,
                               carpeta_salida: str = SALIDA_DEFAULT) -> dict:
    """
    Ejecuta el preprocesamiento completo y retorna rutas de los rasters
    listos para ingresar al modelo de zonas de calor.

    Retorna dict con claves: 'lst', 'ndvi', 'localidades'
    """
    os.makedirs(carpeta_salida, exist_ok=True)

    print("\n" + "="*60)
    print("PREPROCESAMIENTO LANDSAT — CARTAGENA DE INDIAS")
    print("="*60)

    # ── Detectar bandas ──────────────────────────────────
    print("\n[1/4] Detectando bandas en carpeta Landsat...")
    bandas = detectar_bandas(carpeta_landsat)

    # Nombre base de la escena (ej: LC09_L2SP_008053_20240115)
    nombre_escena = os.path.basename(bandas["B10"]).split("_B10")[0].split("_ST_B10")[0]
    print(f"  Escena identificada: {nombre_escena}")

    # ── Calcular LST ─────────────────────────────────────
    print("\n[2/4] Calculando LST desde B10...")
    lst_raw  = os.path.join(carpeta_salida, f"{nombre_escena}_LST_raw.tif")
    lst_path = os.path.join(carpeta_salida, "LST_cartagena.tif")
    calcular_lst(bandas["B10"], lst_raw)
    reproyectar_a_wgs84(lst_raw, lst_path)
    if lst_raw != lst_path:
        os.remove(lst_raw)

    # ── Calcular NDVI ────────────────────────────────────
    print("\n[3/4] Calculando NDVI desde B4 y B5...")
    ndvi_raw  = os.path.join(carpeta_salida, f"{nombre_escena}_NDVI_raw.tif")
    ndvi_path = os.path.join(carpeta_salida, "NDVI_cartagena.tif")
    calcular_ndvi(bandas["B4"], bandas["B5"], ndvi_raw)
    reproyectar_a_wgs84(ndvi_raw, ndvi_path)
    if ndvi_raw != ndvi_path:
        os.remove(ndvi_raw)

    # ── Cargar localidades ───────────────────────────────
    print("\n[4/4] Cargando límites de localidades...")
    if shapefile_localidades and os.path.exists(shapefile_localidades):
        localidades = cargar_localidades_oficial(shapefile_localidades)
    else:
        if shapefile_localidades:
            print(f"  Shapefile no encontrado: {shapefile_localidades}")
        localidades = localidades_aproximadas()

    # Guardar localidades procesadas como GeoPackage
    loc_path = os.path.join(carpeta_salida, "..", "localidades_cartagena.gpkg")
    localidades.to_file(loc_path, driver="GPKG")
    print(f"  Localidades guardadas: {loc_path}")

    print("\n" + "="*60)
    print("PREPROCESAMIENTO COMPLETADO")
    print(f"  LST   → {lst_path}")
    print(f"  NDVI  → {ndvi_path}")
    print(f"  Para continuar ejecuta:")
    print(f"    python modelacion_zonas_calor.py \\")
    print(f"      --lst  {lst_path} \\")
    print(f"      --ndvi {ndvi_path}")
    print("="*60 + "\n")

    return {"lst": lst_path, "ndvi": ndvi_path, "localidades": localidades}


# ──────────────────────────────────────────────────────────
# PUNTO DE ENTRADA
# ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Preprocesamiento Landsat → LST y NDVI para Cartagena de Indias"
    )
    parser.add_argument(
        "--carpeta_landsat", required=True,
        help="Carpeta con los archivos .TIF de la escena Landsat (B4, B5, B10)"
    )
    parser.add_argument(
        "--shapefile_localidades", default=None,
        help="Ruta al shapefile .shp oficial de localidades (opcional)"
    )
    parser.add_argument(
        "--salida", default=SALIDA_DEFAULT,
        help=f"Carpeta de salida para los rasters (default: {SALIDA_DEFAULT})"
    )
    args = parser.parse_args()

    resultado = ejecutar_preprocesamiento(
        carpeta_landsat=args.carpeta_landsat,
        shapefile_localidades=args.shapefile_localidades,
        carpeta_salida=args.salida,
    )
