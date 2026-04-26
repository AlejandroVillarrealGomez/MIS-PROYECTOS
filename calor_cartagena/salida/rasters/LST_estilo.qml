<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34" styleCategories="AllStyleCategories">
  <pipe>
    <rasterrenderer type="singlebandpseudocolor" band="1" opacity="0.85"
                    classificationMin="26" classificationMax="48">
      <rastershader>
        <colorrampshader colorRampType="INTERPOLATED" clip="0" labelPrecision="1">
          <item value="26"  color="#313695" label="26°C" alpha="255"/>
          <item value="30"  color="#4575b4" label="30°C" alpha="255"/>
          <item value="33"  color="#74add1" label="33°C" alpha="255"/>
          <item value="35"  color="#abd9e9" label="35°C" alpha="255"/>
          <item value="37"  color="#fee090" label="37°C" alpha="255"/>
          <item value="39"  color="#fdae61" label="39°C" alpha="255"/>
          <item value="41"  color="#f46d43" label="41°C" alpha="255"/>
          <item value="44"  color="#d73027" label="44°C" alpha="255"/>
          <item value="48"  color="#a50026" label="48°C" alpha="255"/>
        </colorrampshader>
      </rastershader>
    </rasterrenderer>
    <brightnesscontrast brightness="0" contrast="0"/>
    <huesaturation saturation="0"/>
    <rasterresampler maxOversampling="2"/>
  </pipe>
</qgis>
