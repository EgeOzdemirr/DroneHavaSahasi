Offline harita varlıkları bu klasörde tutulur.

Yapı:
- `tiles/<layer>/<z>/<x>/<y>.png`: offline OSM tile klasörü
- `tiles/manifest.json`: katman manifesti

Hazırlama:
- `python scripts/fetch_offline_map.py`

Varsayılan offline katmanlar:
- `world`: dünya genel görünümü, zoom `2..5`
- `turkiye`: Türkiye geneli, zoom `5..10`
- `istanbul`: İstanbul bölgesi, zoom `9..13`
- `tuzla`: İstanbul/Tuzla detay bölgesi, zoom `12..16`

Not:
- `MAP_PROVIDER=openfreemap` kullanıldığında dünya geneli harita OpenFreeMap/MapLibre üzerinden gelir ve bu offline raster paketler sadece fallback olur.
- `MAP_PROVIDER=offline` kullanıldığında harita zemini tamamen yerel dosyalardan servis edilir.
- UI tarafında Leaflet yerel olarak `app/ui/static/vendor/leaflet` altından yüklenir.
