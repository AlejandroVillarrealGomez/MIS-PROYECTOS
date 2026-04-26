<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34" styleCategories="AllStyleCategories">
  <renderer-v2 type="categorizedSymbol" attr="zona_calor" enableorderby="0" forceraster="0">
    <categories>
      <category value="1" label="Zona 1 — Muy Baja" render="true">
        <symbol type="fill" name="1" alpha="0.85">
          <layer class="SimpleFill">
            <Option type="Map">
              <Option name="color" value="33,102,172,255" type="QString"/>
              <Option name="outline_color" value="255,255,255,180" type="QString"/>
              <Option name="outline_width" value="0.1" type="QString"/>
              <Option name="style" value="solid" type="QString"/>
            </Option>
          </layer>
        </symbol>
      </category>
      <category value="2" label="Zona 2 — Baja" render="true">
        <symbol type="fill" name="2" alpha="0.85">
          <layer class="SimpleFill">
            <Option type="Map">
              <Option name="color" value="116,173,209,255" type="QString"/>
              <Option name="outline_color" value="255,255,255,180" type="QString"/>
              <Option name="outline_width" value="0.1" type="QString"/>
              <Option name="style" value="solid" type="QString"/>
            </Option>
          </layer>
        </symbol>
      </category>
      <category value="3" label="Zona 3 — Media" render="true">
        <symbol type="fill" name="3" alpha="0.85">
          <layer class="SimpleFill">
            <Option type="Map">
              <Option name="color" value="254,224,144,255" type="QString"/>
              <Option name="outline_color" value="255,255,255,180" type="QString"/>
              <Option name="outline_width" value="0.1" type="QString"/>
              <Option name="style" value="solid" type="QString"/>
            </Option>
          </layer>
        </symbol>
      </category>
      <category value="4" label="Zona 4 — Alta" render="true">
        <symbol type="fill" name="4" alpha="0.85">
          <layer class="SimpleFill">
            <Option type="Map">
              <Option name="color" value="244,109,67,255" type="QString"/>
              <Option name="outline_color" value="255,255,255,180" type="QString"/>
              <Option name="outline_width" value="0.1" type="QString"/>
              <Option name="style" value="solid" type="QString"/>
            </Option>
          </layer>
        </symbol>
      </category>
      <category value="5" label="Zona 5 — Muy Alta" render="true">
        <symbol type="fill" name="5" alpha="0.85">
          <layer class="SimpleFill">
            <Option type="Map">
              <Option name="color" value="165,0,38,255" type="QString"/>
              <Option name="outline_color" value="255,255,255,180" type="QString"/>
              <Option name="outline_width" value="0.1" type="QString"/>
              <Option name="style" value="solid" type="QString"/>
            </Option>
          </layer>
        </symbol>
      </category>
    </categories>
    <rotation/>
    <sizescale/>
  </renderer-v2>
  <labeling type="simple">
    <settings>
      <text-style fontFamily="Arial" fontSize="8" fontWeight="50"
                  textColor="0,0,0,255" isExpression="1"
                  fieldName="concat(nombre_zon, '\n', round(area_ha,1), ' ha')"/>
      <text-buffer bufferEnabled="1" bufferSize="1" bufferColor="255,255,255,200"/>
      <placement placement="1" centroidWhole="0"/>
      <rendering scaleVisibility="1" scaleMin="1" scaleMax="100000"/>
    </settings>
  </labeling>
  <layerGeometryType>2</layerGeometryType>
</qgis>
