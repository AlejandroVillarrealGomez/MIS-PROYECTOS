"""
Modelación de Zonas de Calor Urbano - Cartagena de Indias
=========================================================
Genera shapefiles de zonas de calor por localidad usando:
  - Temperatura Superficial del Suelo (LST) simulada / real (GeoTIFF)
  - Índice de Vegetación Normalizado (NDVI) simulado / real (GeoTIFF)
  - Límites administrativos de las 3 localidades de Cartagena

Salidas:
  salida/shapefiles/   -> zonas_calor_<localidad>.shp  (polígonos clasificados)
  salida/rasters/      -> LST_cartagena.tif, NDVI_cartagena.tif
  salida/mapas/        -> mapa_calor_<localidad>.png
"""

import numpy as np
import geopandas as gpd
import rasterio
from rasterio.transform import from_bounds
from rasterio.features import shapes, rasterize
from rasterio.mask import mask as rasterio_mask
import pandas as pd
from shapely.geometry import Polygon, MultiPolygon, shape, mapping
from shapely.ops import unary_union
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.patches import Patch
from scipy.ndimage import gaussian_filter
import warnings
import os

warnings.filterwarnings("ignore")

# ──────────────────────────────────────────────
# 1. PARÁMETROS GLOBALES
# ──────────────────────────────────────────────
CRS_GEO   = "EPSG:4326"
CRS_PROJ  = "EPSG:9377"   # MAGNA-SIRGAS / Colombia Oeste (metros)
RESOLUCION_M = 30         # 30 m ≈ resolución Landsat

OUTPUT_DIR = "/home/user/MIS-PROYECTOS/calor_cartagena/salida"

CLASES_CALOR = {
    1: ("Muy Baja",   "#2166ac"),
    2: ("Baja",       "#74add1"),
    3: ("Media",      "#fee090"),
    4: ("Alta",       "#f46d43"),
    5: ("Muy Alta",   "#a50026"),
}

# ──────────────────────────────────────────────
# 2. GEOMETRÍAS APROXIMADAS DE LAS LOCALIDADES
#    (polígonos basados en división oficial IGAC)
# ──────────────────────────────────────────────

def crear_localidades_cartagena() -> gpd.GeoDataFrame:
    """
    Polígonos aproximados de las 3 localidades oficiales de Cartagena de Indias
    según el Acuerdo 006 de 2003 del Concejo Distrital.
    Coordenadas en WGS84 (EPSG:4326).
    """
    localidades = {
        "LOCALIDAD_1": {
            "nombre":    "Histórica y del Caribe Norte",
            "codigo":    "CTG-L1",
            "area_km2":  68.5,
            # Casco histórico, Bocagrande, Manga, Marbella, Crespo,
            # El Cabrero, Castillogrande, El Laguito
            "geom": Polygon([
                (-75.608, 10.390), (-75.590, 10.380), (-75.562, 10.372),
                (-75.548, 10.378), (-75.535, 10.394), (-75.523, 10.408),
                (-75.518, 10.423), (-75.521, 10.438), (-75.530, 10.448),
                (-75.543, 10.456), (-75.558, 10.462), (-75.572, 10.458),
                (-75.582, 10.447), (-75.592, 10.430), (-75.600, 10.415),
                (-75.608, 10.390),
            ]),
        },
        "LOCALIDAD_2": {
            "nombre":    "De la Virgen y Turística",
            "codigo":    "CTG-L2",
            "area_km2":  571.4,
            # La Boquilla, Manzanillo del Mar, Punta Canoa, Pontezuela,
            # Bayunca, La Popa, Ternera
            "geom": Polygon([
                (-75.558, 10.462), (-75.543, 10.456), (-75.530, 10.448),
                (-75.521, 10.438), (-75.518, 10.423), (-75.508, 10.432),
                (-75.498, 10.448), (-75.488, 10.465), (-75.482, 10.482),
                (-75.480, 10.500), (-75.485, 10.518), (-75.495, 10.532),
                (-75.510, 10.540), (-75.528, 10.545), (-75.545, 10.540),
                (-75.560, 10.530), (-75.570, 10.515), (-75.572, 10.498),
                (-75.568, 10.482), (-75.560, 10.470), (-75.558, 10.462),
            ]),
        },
        "LOCALIDAD_3": {
            "nombre":    "Industrial y de la Bahía",
            "codigo":    "CTG-L3",
            "area_km2":  154.3,
            # Mamonal, Pasacaballos, Zona Industrial,
            # Islas del Rosario (continental)
            "geom": Polygon([
                (-75.608, 10.390), (-75.600, 10.415), (-75.592, 10.430),
                (-75.582, 10.447), (-75.572, 10.458), (-75.558, 10.462),
                (-75.560, 10.470), (-75.568, 10.482), (-75.575, 10.468),
                (-75.585, 10.452), (-75.595, 10.438), (-75.605, 10.422),
                (-75.618, 10.405), (-75.625, 10.388), (-75.622, 10.372),
                (-75.610, 10.360), (-75.598, 10.352), (-75.585, 10.355),
                (-75.574, 10.363), (-75.565, 10.374), (-75.562, 10.372),
                (-75.590, 10.380), (-75.608, 10.390),
            ]),
        },
    }

    records = []
    for key, data in localidades.items():
        records.append({
            "id":       key,
            "nombre":   data["nombre"],
            "codigo":   data["codigo"],
            "area_km2": data["area_km2"],
            "geometry": data["geom"],
        })

    gdf = gpd.GeoDataFrame(records, crs=CRS_GEO)
    return gdf


# ──────────────────────────────────────────────
# 3. GENERACIÓN DE RASTERS SINTÉTICOS
#    (LST y NDVI con patrones urbanos realistas)
# ──────────────────────────────────────────────

def _bbox_from_gdf(gdf: gpd.GeoDataFrame, buffer_deg: float = 0.01):
    bounds = gdf.total_bounds   # (minx, miny, maxx, maxy)
    return (
        bounds[0] - buffer_deg,
        bounds[1] - buffer_deg,
        bounds[2] + buffer_deg,
        bounds[3] + buffer_deg,
    )


def generar_rasters_sinteticos(gdf: gpd.GeoDataFrame):
    """
    Genera rasters de LST (°C) y NDVI [-1,1] con patrones urbanos realistas:
      - Centros densos → LST alta, NDVI bajo
      - Zonas verdes/manglar → LST baja, NDVI alto
      - Industria → LST muy alta
    """
    minx, miny, maxx, maxy = _bbox_from_gdf(gdf)

    # Tamaño de píxel en grados (~30 m a 10°N)
    px = RESOLUCION_M / 111_320.0

    cols = int((maxx - minx) / px)
    rows = int((maxy - miny) / px)
    transform = from_bounds(minx, miny, maxx, maxy, cols, rows)

    # Coordenadas de cada píxel
    xs = np.linspace(minx, maxx, cols)
    ys = np.linspace(maxy, miny, rows)
    XX, YY = np.meshgrid(xs, ys)

    # ── LST base (°C) ──────────────────────────────────────────────────────
    # Temperatura de fondo tropical: 28 – 32 °C
    np.random.seed(42)
    lst = 30.0 + gaussian_filter(np.random.randn(rows, cols) * 1.5, sigma=8)

    # Isla de calor urbano: centro histórico (~10.424°N, -75.551°W)
    def isla_calor(cx, cy, intensidad, radio):
        d2 = ((XX - cx) ** 2 + (YY - cy) ** 2)
        return intensidad * np.exp(-d2 / (2 * radio ** 2))

    lst += isla_calor(-75.551, 10.424, 6.0, 0.022)   # Centro histórico
    lst += isla_calor(-75.548, 10.412, 4.5, 0.015)   # Bocagrande
    lst += isla_calor(-75.595, 10.368, 8.0, 0.025)   # Zona industrial Mamonal
    lst += isla_calor(-75.525, 10.440, 3.5, 0.018)   # Crespo / Aeropuerto
    lst += isla_calor(-75.500, 10.470, 2.5, 0.020)   # Ternera

    # Enfriamiento por vegetación / manglar (La Boquilla ~10.495°N)
    def zona_fria(cx, cy, delta, radio):
        d2 = ((XX - cx) ** 2 + (YY - cy) ** 2)
        return -delta * np.exp(-d2 / (2 * radio ** 2))

    lst += zona_fria(-75.500, 10.520, 4.0, 0.018)   # Manglar La Boquilla
    lst += zona_fria(-75.540, 10.510, 2.5, 0.015)   # Pontezuela / verde
    lst += zona_fria(-75.565, 10.445, 2.0, 0.010)   # Parques Bocagrande

    lst = np.clip(lst, 24.0, 48.0)

    # ── NDVI ──────────────────────────────────────────────────────────────
    # NDVI = -0.3 (asfalto) … 0.8 (vegetación densa)
    ndvi = -0.15 + gaussian_filter(np.random.randn(rows, cols) * 0.12, sigma=6)

    # Correlación inversa con LST
    ndvi -= (lst - 30.0) * 0.025
    ndvi += zona_fria(-75.500, 10.520, -0.45, 0.018)[...] * (-1)   # manglar verde
    ndvi += zona_fria(-75.540, 10.510, -0.30, 0.015)[...] * (-1)
    ndvi = np.clip(ndvi, -0.40, 0.82)

    # ── Guardar rasters ────────────────────────────────────────────────────
    profile = {
        "driver":    "GTiff",
        "dtype":     "float32",
        "width":     cols,
        "height":    rows,
        "count":     1,
        "crs":       CRS_GEO,
        "transform": transform,
        "compress":  "lzw",
    }

    lst_path  = os.path.join(OUTPUT_DIR, "rasters", "LST_cartagena.tif")
    ndvi_path = os.path.join(OUTPUT_DIR, "rasters", "NDVI_cartagena.tif")

    with rasterio.open(lst_path, "w", **profile) as dst:
        dst.write(lst.astype("float32"), 1)
        dst.update_tags(descripcion="LST simulada Cartagena °C", fuente="Modelo sintético basado en patrones urbanos")

    with rasterio.open(ndvi_path, "w", **profile) as dst:
        dst.write(ndvi.astype("float32"), 1)
        dst.update_tags(descripcion="NDVI simulado Cartagena", fuente="Modelo sintético")

    print(f"  Rasters generados: {rows}x{cols} px  (resolución ~{RESOLUCION_M} m)")
    return lst_path, ndvi_path, transform, (rows, cols)


# ──────────────────────────────────────────────
# 4. CARGA DE RASTERS REALES (OPCIONAL)
# ──────────────────────────────────────────────

def cargar_raster_real(ruta: str):
    """Carga un GeoTIFF real y retorna (array, transform, crs)."""
    with rasterio.open(ruta) as src:
        data = src.read(1).astype("float32")
        nodata = src.nodata
        if nodata is not None:
            data[data == nodata] = np.nan
        return data, src.transform, str(src.crs), src.meta.copy()


# ──────────────────────────────────────────────
# 5. CLASIFICACIÓN EN ZONAS DE CALOR
# ──────────────────────────────────────────────

def clasificar_zonas_calor(lst_arr: np.ndarray,
                            ndvi_arr: np.ndarray,
                            percentiles=(20, 40, 60, 80)) -> np.ndarray:
    """
    Índice combinado (ICZ) = 0.65·LST_norm + 0.35·(1 - NDVI_norm)
    Clasificado en 5 categorías por percentiles.
    """
    def normalizar(arr):
        a_min, a_max = np.nanpercentile(arr, 2), np.nanpercentile(arr, 98)
        return np.clip((arr - a_min) / (a_max - a_min + 1e-9), 0, 1)

    lst_n  = normalizar(lst_arr)
    ndvi_n = normalizar(ndvi_arr)

    icz = 0.65 * lst_n + 0.35 * (1.0 - ndvi_n)

    p20, p40, p60, p80 = [np.nanpercentile(icz, p) for p in percentiles]

    zonas = np.zeros_like(icz, dtype="uint8")
    zonas[icz <= p20]                    = 1
    zonas[(icz > p20) & (icz <= p40)]   = 2
    zonas[(icz > p40) & (icz <= p60)]   = 3
    zonas[(icz > p60) & (icz <= p80)]   = 4
    zonas[icz > p80]                     = 5

    return zonas, icz


# ──────────────────────────────────────────────
# 6. VECTORIZACIÓN Y RECORTE POR LOCALIDAD
# ──────────────────────────────────────────────

def vectorizar_zonas(zonas_arr: np.ndarray,
                     transform,
                     crs: str) -> gpd.GeoDataFrame:
    """Convierte el raster clasificado en polígonos vectoriales."""
    mask_valid = zonas_arr > 0
    geoms = []
    for geom_json, val in shapes(zonas_arr, mask=mask_valid, transform=transform):
        geoms.append({"geometry": shape(geom_json), "zona_calor": int(val)})

    if not geoms:
        return gpd.GeoDataFrame(columns=["geometry", "zona_calor"], crs=crs)

    gdf = gpd.GeoDataFrame(geoms, crs=crs)
    # Disolver por clase para simplificar geometría
    gdf = gdf.dissolve(by="zona_calor").reset_index()
    gdf["nombre_zona"] = gdf["zona_calor"].map(
        {k: v[0] for k, v in CLASES_CALOR.items()}
    )
    return gdf


def recortar_por_localidad(zonas_gdf: gpd.GeoDataFrame,
                            localidades_gdf: gpd.GeoDataFrame) -> dict:
    """
    Intersecta las zonas de calor con cada localidad.
    Retorna {nombre_localidad: GeoDataFrame}.
    """
    zonas_gdf = zonas_gdf.to_crs(localidades_gdf.crs)
    resultado = {}
    for _, row in localidades_gdf.iterrows():
        loc_geom = gpd.GeoDataFrame([row], crs=localidades_gdf.crs)
        clip = gpd.overlay(zonas_gdf, loc_geom, how="intersection")
        clip["area_ha"] = clip.to_crs(CRS_PROJ).geometry.area / 10_000
        clip["localidad"]  = row["nombre"]
        clip["cod_loc"]    = row["codigo"]
        resultado[row["nombre"]] = clip
    return resultado


# ──────────────────────────────────────────────
# 7. ESTADÍSTICAS POR LOCALIDAD
# ──────────────────────────────────────────────

def calcular_estadisticas(recortes: dict,
                           lst_path: str,
                           ndvi_path: str,
                           localidades_gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    filas = []
    for _, row_loc in localidades_gdf.iterrows():
        nombre = row_loc["nombre"]
        geom   = [mapping(row_loc.geometry)]

        for ruta, campo in [(lst_path, "lst"), (ndvi_path, "ndvi")]:
            with rasterio.open(ruta) as src:
                try:
                    arr, _ = rasterio_mask(src, geom, crop=True, nodata=np.nan)
                    datos  = arr[0][~np.isnan(arr[0])]
                except Exception:
                    datos = np.array([np.nan])

            if campo == "lst":
                lst_vals = datos
            else:
                ndvi_vals = datos

        clip = recortes.get(nombre, gpd.GeoDataFrame())
        area_total = clip["area_ha"].sum() if not clip.empty else 0

        for zona_id, (zona_nombre, _) in CLASES_CALOR.items():
            sub = clip[clip["zona_calor"] == zona_id] if not clip.empty else pd.DataFrame()
            area_z = sub["area_ha"].sum() if not sub.empty else 0
            filas.append({
                "Localidad":    nombre,
                "Zona_ID":      zona_id,
                "Zona_Nombre":  zona_nombre,
                "Area_ha":      round(area_z, 2),
                "Pct_Local":    round(100 * area_z / area_total, 1) if area_total > 0 else 0,
                "LST_media":    round(float(np.nanmean(lst_vals)), 2),
                "LST_max":      round(float(np.nanmax(lst_vals)), 2),
                "NDVI_medio":   round(float(np.nanmean(ndvi_vals)), 3),
            })

    return pd.DataFrame(filas)


# ──────────────────────────────────────────────
# 8. GUARDAR SHAPEFILES
# ──────────────────────────────────────────────

def guardar_shapefiles(recortes: dict):
    for nombre, gdf in recortes.items():
        if gdf.empty:
            continue
        slug = nombre.replace(" ", "_").replace("/", "-")
        ruta = os.path.join(OUTPUT_DIR, "shapefiles", f"zonas_calor_{slug}.shp")
        gdf.to_crs(CRS_GEO).to_file(ruta, driver="ESRI Shapefile", encoding="utf-8")
        print(f"  Guardado: {ruta}")

    # Shapefile unificado (todas las localidades)
    todas = gpd.GeoDataFrame(
        pd.concat(list(recortes.values()), ignore_index=True),
        crs=CRS_GEO,
    )
    ruta_total = os.path.join(OUTPUT_DIR, "shapefiles", "zonas_calor_CARTAGENA_completo.shp")
    todas.to_file(ruta_total, driver="ESRI Shapefile", encoding="utf-8")
    print(f"  Guardado: {ruta_total}")


# ──────────────────────────────────────────────
# 9. VISUALIZACIÓN
# ──────────────────────────────────────────────

def generar_mapa_localidad(nombre: str,
                            clip_gdf: gpd.GeoDataFrame,
                            loc_geom,
                            lst_path: str,
                            ndvi_path: str):
    fig, axes = plt.subplots(1, 3, figsize=(18, 7))
    fig.suptitle(
        f"Zonas de Calor Urbano — {nombre}\nCartagena de Indias, Colombia",
        fontsize=14, fontweight="bold", y=1.01,
    )

    geom_list = [mapping(loc_geom)]

    # ── LST recortada ─────────────────────────────────────────────────────
    ax = axes[0]
    with rasterio.open(lst_path) as src:
        arr, t = rasterio_mask(src, geom_list, crop=True, nodata=np.nan)
    im0 = ax.imshow(arr[0], cmap="hot", vmin=26, vmax=46,
                    extent=[t.c, t.c + t.a * arr.shape[2],
                            t.f + t.e * arr.shape[1], t.f])
    plt.colorbar(im0, ax=ax, label="°C", fraction=0.046)
    ax.set_title("Temperatura Superficial (LST)")
    ax.set_xlabel("Longitud"); ax.set_ylabel("Latitud")

    # ── NDVI recortado ────────────────────────────────────────────────────
    ax = axes[1]
    with rasterio.open(ndvi_path) as src:
        arr2, t2 = rasterio_mask(src, geom_list, crop=True, nodata=np.nan)
    im1 = ax.imshow(arr2[0], cmap="RdYlGn", vmin=-0.35, vmax=0.80,
                    extent=[t2.c, t2.c + t2.a * arr2.shape[2],
                            t2.f + t2.e * arr2.shape[1], t2.f])
    plt.colorbar(im1, ax=ax, label="NDVI", fraction=0.046)
    ax.set_title("Índice Vegetación (NDVI)")
    ax.set_xlabel("Longitud")

    # ── Zonas de calor vectorizadas ───────────────────────────────────────
    ax = axes[2]
    if not clip_gdf.empty:
        color_map = {k: v[1] for k, v in CLASES_CALOR.items()}
        for zona_id in sorted(clip_gdf["zona_calor"].unique()):
            sub = clip_gdf[clip_gdf["zona_calor"] == zona_id]
            sub.plot(ax=ax, color=color_map.get(zona_id, "#cccccc"),
                     edgecolor="none", alpha=0.85)
    loc_gdf = gpd.GeoDataFrame(geometry=[loc_geom], crs=CRS_GEO)
    loc_gdf.boundary.plot(ax=ax, color="black", linewidth=1.2)
    leyenda = [
        Patch(facecolor=v[1], label=f"{k}. {v[0]}")
        for k, v in CLASES_CALOR.items()
    ]
    ax.legend(handles=leyenda, title="Zona de Calor", loc="lower right",
              fontsize=8, title_fontsize=8)
    ax.set_title("Clasificación Zonas de Calor")
    ax.set_xlabel("Longitud")

    plt.tight_layout()
    slug = nombre.replace(" ", "_").replace("/", "-")
    ruta = os.path.join(OUTPUT_DIR, "mapas", f"mapa_calor_{slug}.png")
    plt.savefig(ruta, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Mapa: {ruta}")


def generar_mapa_resumen(localidades_gdf: gpd.GeoDataFrame,
                          recortes: dict):
    fig, ax = plt.subplots(1, 1, figsize=(12, 10))
    ax.set_title(
        "Mapa de Zonas de Calor Urbano\nCartagena de Indias — por Localidad",
        fontsize=14, fontweight="bold",
    )
    color_map = {k: v[1] for k, v in CLASES_CALOR.items()}

    for nombre, gdf in recortes.items():
        if gdf.empty:
            continue
        for zona_id in sorted(gdf["zona_calor"].unique()):
            sub = gdf[gdf["zona_calor"] == zona_id]
            sub.plot(ax=ax, color=color_map.get(zona_id, "#ccc"),
                     edgecolor="none", alpha=0.80)

    localidades_gdf.boundary.plot(ax=ax, color="black", linewidth=1.5)
    for _, row in localidades_gdf.iterrows():
        cx, cy = row.geometry.centroid.x, row.geometry.centroid.y
        ax.annotate(row["nombre"], (cx, cy), ha="center", fontsize=8,
                    fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.6))

    leyenda = [
        Patch(facecolor=v[1], label=f"Zona {k} — {v[0]}")
        for k, v in CLASES_CALOR.items()
    ]
    ax.legend(handles=leyenda, title="Intensidad Zona Calor",
              loc="upper right", fontsize=9)
    ax.set_xlabel("Longitud"); ax.set_ylabel("Latitud")

    ruta = os.path.join(OUTPUT_DIR, "mapas", "mapa_calor_CARTAGENA_completo.png")
    plt.savefig(ruta, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Mapa general: {ruta}")


# ──────────────────────────────────────────────
# 10. PIPELINE PRINCIPAL
# ──────────────────────────────────────────────

def ejecutar_pipeline(lst_real: str = None, ndvi_real: str = None):
    """
    Parámetros opcionales:
      lst_real  -> ruta a un GeoTIFF real de LST (Landsat/MODIS)
      ndvi_real -> ruta a un GeoTIFF real de NDVI
    Si no se proveen, se usan datos sintéticos representativos.
    """
    print("\n" + "="*60)
    print("MODELACIÓN DE ZONAS DE CALOR — CARTAGENA DE INDIAS")
    print("="*60)

    # 1. Localidades
    print("\n[1/6] Cargando límites de localidades...")
    localidades = crear_localidades_cartagena()
    print(f"      {len(localidades)} localidades cargadas")

    # 2. Rasters
    print("\n[2/6] Preparando rasters LST y NDVI...")
    if lst_real and ndvi_real:
        print("      Usando rasters reales proporcionados.")
        lst_path  = lst_real
        ndvi_path = ndvi_real
    else:
        print("      Generando rasters sintéticos (no se proporcionaron datos reales).")
        lst_path, ndvi_path, transform, shape_rc = generar_rasters_sinteticos(localidades)

    # 3. Leer arrays
    print("\n[3/6] Leyendo y clasificando rasters...")
    with rasterio.open(lst_path) as src:
        lst_arr   = src.read(1).astype("float32")
        transform = src.transform
        crs_rast  = str(src.crs)
    with rasterio.open(ndvi_path) as src:
        ndvi_arr = src.read(1).astype("float32")

    zonas_arr, icz_arr = clasificar_zonas_calor(lst_arr, ndvi_arr)
    print(f"      Valores únicos de zonas: {np.unique(zonas_arr)}")

    # 4. Vectorizar y recortar
    print("\n[4/6] Vectorizando y recortando por localidad...")
    zonas_gdf = vectorizar_zonas(zonas_arr, transform, crs_rast)
    recortes  = recortar_por_localidad(zonas_gdf, localidades)

    # 5. Estadísticas
    print("\n[5/6] Calculando estadísticas...")
    stats = calcular_estadisticas(recortes, lst_path, ndvi_path, localidades)
    stats_path = os.path.join(OUTPUT_DIR, "estadisticas_zonas_calor.csv")
    stats.to_csv(stats_path, index=False, encoding="utf-8-sig")
    print(f"\n{'─'*58}")
    print(stats.to_string(index=False))
    print(f"{'─'*58}")
    print(f"\n  Estadísticas guardadas: {stats_path}")

    # 6. Guardar shapefiles
    print("\n[6a/6] Guardando shapefiles...")
    guardar_shapefiles(recortes)

    # 6b. Mapas
    print("\n[6b/6] Generando mapas...")
    for _, row in localidades.iterrows():
        generar_mapa_localidad(
            row["nombre"],
            recortes.get(row["nombre"], gpd.GeoDataFrame()),
            row.geometry,
            lst_path, ndvi_path,
        )
    generar_mapa_resumen(localidades, recortes)

    print("\n" + "="*60)
    print("PROCESO COMPLETADO")
    print(f"  Shapefiles  -> {OUTPUT_DIR}/shapefiles/")
    print(f"  Mapas       -> {OUTPUT_DIR}/mapas/")
    print(f"  Rasters     -> {OUTPUT_DIR}/rasters/")
    print(f"  Estadísticas-> {stats_path}")
    print("="*60 + "\n")
    return stats


# ──────────────────────────────────────────────
# PUNTO DE ENTRADA
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Modelación de Zonas de Calor Urbano — Cartagena de Indias"
    )
    parser.add_argument("--lst",  type=str, default=None,
                        help="Ruta GeoTIFF de LST real (opcional)")
    parser.add_argument("--ndvi", type=str, default=None,
                        help="Ruta GeoTIFF de NDVI real (opcional)")
    args = parser.parse_args()
    ejecutar_pipeline(lst_real=args.lst, ndvi_real=args.ndvi)
