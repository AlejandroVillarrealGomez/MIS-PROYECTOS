<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34" styleCategories="AllStyleCategories">
  <pipe>
    <rasterrenderer type="singlebandpseudocolor" band="1" opacity="0.85"
                    classificationMin="-0.35" classificationMax="0.82">
      <rastershader>
        <colorrampshader colorRampType="INTERPOLATED" clip="0" labelPrecision="2">
          <item value="-0.35" color="#8c510a" label="-0.35 Agua/Asf." alpha="255"/>
          <item value="0.0"   color="#d8b365" label="0.00 Suelo"      alpha="255"/>
          <item value="0.1"   color="#f6e8c3" label="0.10 Veg.escasa" alpha="255"/>
          <item value="0.2"   color="#c7e9c0" label="0.20 Veg.baja"   alpha="255"/>
          <item value="0.35"  color="#74c476" label="0.35 Veg.media"  alpha="255"/>
          <item value="0.5"   color="#31a354" label="0.50 Veg.alta"   alpha="255"/>
          <item value="0.65"  color="#006d2c" label="0.65 Manglar"    alpha="255"/>
          <item value="0.82"  color="#00441b" label="0.82 Bosque"     alpha="255"/>
        </colorrampshader>
      </rastershader>
    </rasterrenderer>
    <brightnesscontrast brightness="0" contrast="0"/>
    <huesaturation saturation="0"/>
    <rasterresampler maxOversampling="2"/>
  </pipe>
</qgis>
