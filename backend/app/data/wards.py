"""Hyperlocal ward registry.

Each entry is a ward / neighbourhood inside a city -- NOT a city or district.
Mein Kaivinai's unit of analysis is the ward, because heat risk varies sharply
within a single city: a dense market ward and a river-side ward 4 km apart can
differ by several degrees of felt heat.

Two kinds of data live here, and they are deliberately kept apart:

1. `lat` / `lon` -- approximate ward centroids. These are sent to Open-Meteo,
   which returns the REAL weather for that point. No weather value is stored here.

2. The land-cover profile (`built_up`, `green`, `water`, `industrial`, `density`)
   -- static geographic characteristics of the ward on a 0-1 scale. These are
   INDICATIVE prototype values compiled from open reference material (OpenStreetMap
   land use, city master plans, visual survey of satellite imagery). They are NOT
   measurements and they are NOT weather. They feed the urban-heat-island
   adjustment in services/local_context.py, which is labelled as a model everywhere
   it surfaces in the UI.

   To replace them with real data, implement LandCoverProvider in
   services/local_context.py against a satellite LULC / land-surface-temperature
   source (Bhuvan LULC, Sentinel-2 NDVI, Landsat 8/9 thermal). Nothing else changes.

Profile scale reference:
  built_up   0 = open land/farmland,      1 = continuous concrete & asphalt
  green      0 = no vegetation,           1 = dense tree canopy / park / forest
  water      0 = no water body near,      1 = directly on sea front or large lake
  industrial 0 = purely residential,      1 = heavy industry / foundry / port yard
  density    0 = sparse peri-urban,       1 = very high residential crowding
"""
from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class Ward:
    id: str
    name: str
    name_ta: str
    city: str
    city_ta: str
    lat: float
    lon: float
    built_up: float
    green: float
    water: float
    industrial: float
    density: float

    def profile(self) -> dict:
        return {"built_up": self.built_up, "green": self.green, "water": self.water,
                "industrial": self.industrial, "density": self.density}

    def brief(self) -> dict:
        d = asdict(self)
        return {"id": d["id"], "name": d["name"], "name_ta": d["name_ta"], "city": d["city"],
                "city_ta": d["city_ta"], "latitude": d["lat"], "longitude": d["lon"],
                "land_cover": self.profile()}


# ---------------------------------------------------------------- Chennai
CHENNAI = [
    Ward("che-royapuram", "Royapuram", "இராயபுரம்", "Chennai", "சென்னை", 13.1143, 80.2940, 0.88, 0.05, 0.85, 0.70, 0.90),
    Ward("che-george-town", "George Town", "ஜார்ஜ் டவுன்", "Chennai", "சென்னை", 13.0920, 80.2870, 0.95, 0.03, 0.55, 0.45, 0.95),
    Ward("che-tondiarpet", "Tondiarpet", "தண்டையார்பேட்டை", "Chennai", "சென்னை", 13.1300, 80.2870, 0.85, 0.06, 0.70, 0.80, 0.85),
    Ward("che-anna-nagar", "Anna Nagar", "அண்ணா நகர்", "Chennai", "சென்னை", 13.0850, 80.2101, 0.72, 0.30, 0.10, 0.10, 0.65),
    Ward("che-t-nagar", "T. Nagar", "தி. நகர்", "Chennai", "சென்னை", 13.0418, 80.2341, 0.94, 0.06, 0.05, 0.15, 0.95),
    Ward("che-nungambakkam", "Nungambakkam", "நுங்கம்பாக்கம்", "Chennai", "சென்னை", 13.0569, 80.2425, 0.80, 0.22, 0.08, 0.10, 0.70),
    Ward("che-mylapore", "Mylapore", "மயிலாப்பூர்", "Chennai", "சென்னை", 13.0339, 80.2698, 0.85, 0.12, 0.60, 0.05, 0.85),
    Ward("che-adyar", "Adyar", "அடையாறு", "Chennai", "சென்னை", 13.0067, 80.2570, 0.62, 0.38, 0.70, 0.05, 0.60),
    Ward("che-guindy", "Guindy", "கிண்டி", "Chennai", "சென்னை", 13.0067, 80.2206, 0.68, 0.42, 0.15, 0.55, 0.50),
    Ward("che-kodambakkam", "Kodambakkam", "கோடம்பாக்கம்", "Chennai", "சென்னை", 13.0510, 80.2260, 0.88, 0.10, 0.05, 0.12, 0.88),
    Ward("che-velachery", "Velachery", "வேளச்சேரி", "Chennai", "சென்னை", 12.9756, 80.2207, 0.82, 0.14, 0.35, 0.10, 0.80),
    Ward("che-perungudi", "Perungudi", "பெருங்குடி", "Chennai", "சென்னை", 12.9650, 80.2450, 0.78, 0.15, 0.40, 0.45, 0.62),
    Ward("che-sholinganallur", "Sholinganallur", "ஷோலிங்கநல்லூர்", "Chennai", "சென்னை", 12.9010, 80.2279, 0.70, 0.20, 0.45, 0.30, 0.55),
    Ward("che-ambattur", "Ambattur", "அம்பத்தூர்", "Chennai", "சென்னை", 13.0983, 80.1614, 0.80, 0.12, 0.20, 0.85, 0.75),
    Ward("che-porur", "Porur", "போரூர்", "Chennai", "சென்னை", 13.0374, 80.1575, 0.72, 0.20, 0.40, 0.25, 0.68),
    Ward("che-madhavaram", "Madhavaram", "மாதவரம்", "Chennai", "சென்னை", 13.1490, 80.2300, 0.62, 0.26, 0.25, 0.50, 0.55),
]

# ---------------------------------------------------------------- Madurai
MADURAI = [
    Ward("mdu-meenakshi", "Meenakshi Temple Area", "மீனாட்சி கோயில் பகுதி", "Madurai", "மதுரை", 9.9195, 78.1193, 0.95, 0.04, 0.10, 0.05, 0.95),
    Ward("mdu-periyar", "Periyar Bus Stand", "பெரியார் பேருந்து நிலையம்", "Madurai", "மதுரை", 9.9175, 78.1250, 0.93, 0.05, 0.08, 0.10, 0.90),
    Ward("mdu-goripalayam", "Goripalayam", "கோரிப்பாளையம்", "Madurai", "மதுரை", 9.9330, 78.1290, 0.88, 0.10, 0.30, 0.08, 0.85),
    Ward("mdu-tallakulam", "Tallakulam", "தல்லாகுளம்", "Madurai", "மதுரை", 9.9420, 78.1280, 0.76, 0.24, 0.25, 0.05, 0.70),
    Ward("mdu-anna-nagar", "Anna Nagar", "அண்ணா நகர்", "Madurai", "மதுரை", 9.9420, 78.1450, 0.70, 0.28, 0.10, 0.05, 0.62),
    Ward("mdu-sellur", "Sellur", "செல்லூர்", "Madurai", "மதுரை", 9.9380, 78.1180, 0.86, 0.10, 0.20, 0.15, 0.88),
    Ward("mdu-kk-nagar", "K.K. Nagar", "கே.கே. நகர்", "Madurai", "மதுரை", 9.9180, 78.0980, 0.74, 0.24, 0.08, 0.08, 0.66),
    Ward("mdu-villapuram", "Villapuram", "விளாப்புரம்", "Madurai", "மதுரை", 9.8950, 78.1200, 0.82, 0.12, 0.10, 0.30, 0.84),
    Ward("mdu-avaniyapuram", "Avaniyapuram", "அவனியாபுரம்", "Madurai", "மதுரை", 9.8850, 78.1080, 0.66, 0.20, 0.30, 0.25, 0.70),
    Ward("mdu-thirunagar", "Thirunagar", "திருநகர்", "Madurai", "மதுரை", 9.8760, 78.0620, 0.58, 0.32, 0.08, 0.20, 0.52),
    Ward("mdu-thiruparankundram", "Thiruparankundram", "திருப்பரங்குன்றம்", "Madurai", "மதுரை", 9.8790, 78.0720, 0.60, 0.30, 0.15, 0.10, 0.58),
    Ward("mdu-kochadai", "Kochadai", "கொச்சடை", "Madurai", "மதுரை", 9.9280, 78.0850, 0.68, 0.22, 0.12, 0.28, 0.66),
    Ward("mdu-vilangudi", "Vilangudi", "விளங்குடி", "Madurai", "மதுரை", 9.9530, 78.0900, 0.56, 0.32, 0.10, 0.18, 0.50),
    Ward("mdu-othakadai", "Othakadai", "ஒத்தக்கடை", "Madurai", "மதுரை", 9.9560, 78.1600, 0.50, 0.38, 0.12, 0.22, 0.44),
    Ward("mdu-uthangudi", "Uthangudi", "உத்தங்குடி", "Madurai", "மதுரை", 9.9600, 78.1800, 0.46, 0.40, 0.10, 0.20, 0.40),
    Ward("mdu-harveypatti", "Harveypatti", "ஹார்வேபட்டி", "Madurai", "மதுரை", 9.9100, 78.0800, 0.62, 0.26, 0.08, 0.32, 0.60),
]

# ---------------------------------------------------------------- Coimbatore
COIMBATORE = [
    Ward("cbe-gandhipuram", "Gandhipuram", "காந்திபுரம்", "Coimbatore", "கோயம்புத்தூர்", 11.0177, 76.9660, 0.93, 0.06, 0.08, 0.12, 0.92),
    Ward("cbe-rs-puram", "R.S. Puram", "ஆர்.எஸ். புரம்", "Coimbatore", "கோயம்புத்தூர்", 11.0060, 76.9490, 0.78, 0.26, 0.10, 0.05, 0.72),
    Ward("cbe-ukkadam", "Ukkadam", "உக்கடம்", "Coimbatore", "கோயம்புத்தூர்", 10.9890, 76.9580, 0.88, 0.08, 0.55, 0.25, 0.90),
    Ward("cbe-peelamedu", "Peelamedu", "பீளமேடு", "Coimbatore", "கோயம்புத்தூர்", 11.0290, 77.0030, 0.80, 0.16, 0.10, 0.45, 0.72),
    Ward("cbe-singanallur", "Singanallur", "சிங்காநல்லூர்", "Coimbatore", "கோயம்புத்தூர்", 11.0050, 77.0290, 0.76, 0.14, 0.45, 0.55, 0.70),
    Ward("cbe-saibaba-colony", "Saibaba Colony", "சாய்பாபா காலனி", "Coimbatore", "கோயம்புத்தூர்", 11.0230, 76.9470, 0.76, 0.26, 0.08, 0.05, 0.68),
    Ward("cbe-ganapathy", "Ganapathy", "கணபதி", "Coimbatore", "கோயம்புத்தூர்", 11.0430, 76.9800, 0.82, 0.12, 0.08, 0.50, 0.78),
    Ward("cbe-saravanampatti", "Saravanampatti", "சரவணம்பட்டி", "Coimbatore", "கோயம்புத்தூர்", 11.0770, 76.9990, 0.68, 0.22, 0.10, 0.30, 0.58),
    Ward("cbe-vadavalli", "Vadavalli", "வடவள்ளி", "Coimbatore", "கோயம்புத்தூர்", 11.0230, 76.8990, 0.54, 0.40, 0.12, 0.08, 0.48),
    Ward("cbe-kuniyamuthur", "Kuniyamuthur", "குனியமுத்தூர்", "Coimbatore", "கோயம்புத்தூர்", 10.9540, 76.9440, 0.66, 0.22, 0.20, 0.40, 0.62),
    Ward("cbe-podanur", "Podanur", "போத்தனூர்", "Coimbatore", "கோயம்புத்தூர்", 10.9670, 76.9520, 0.70, 0.18, 0.15, 0.42, 0.66),
    Ward("cbe-selvapuram", "Selvapuram", "செல்வபுரம்", "Coimbatore", "கோயம்புத்தூர்", 10.9830, 76.9370, 0.74, 0.16, 0.10, 0.35, 0.72),
]

# ---------------------------------------------------------------- Tiruchirappalli
TRICHY = [
    Ward("trz-central", "Central Bus Stand", "மத்திய பேருந்து நிலையம்", "Tiruchirappalli", "திருச்சிராப்பள்ளி", 10.8050, 78.6850, 0.92, 0.06, 0.10, 0.12, 0.90),
    Ward("trz-thillai-nagar", "Thillai Nagar", "தில்லை நகர்", "Tiruchirappalli", "திருச்சிராப்பள்ளி", 10.8200, 78.6870, 0.80, 0.20, 0.15, 0.05, 0.76),
    Ward("trz-srirangam", "Srirangam", "ஸ்ரீரங்கம்", "Tiruchirappalli", "திருச்சிராப்பள்ளி", 10.8620, 78.6920, 0.74, 0.20, 0.70, 0.05, 0.78),
    Ward("trz-woraiyur", "Woraiyur", "உறையூர்", "Tiruchirappalli", "திருச்சிராப்பள்ளி", 10.8330, 78.6820, 0.84, 0.12, 0.25, 0.08, 0.82),
    Ward("trz-kk-nagar", "K.K. Nagar", "கே.கே. நகர்", "Tiruchirappalli", "திருச்சிராப்பள்ளி", 10.8150, 78.6650, 0.72, 0.24, 0.12, 0.08, 0.64),
    Ward("trz-golden-rock", "Golden Rock", "கோல்டன் ராக்", "Tiruchirappalli", "திருச்சிராப்பள்ளி", 10.7790, 78.6960, 0.70, 0.20, 0.10, 0.70, 0.66),
    Ward("trz-ariyamangalam", "Ariyamangalam", "அரியமங்கலம்", "Tiruchirappalli", "திருச்சிராப்பள்ளி", 10.8070, 78.7290, 0.74, 0.14, 0.10, 0.60, 0.70),
    Ward("trz-thiruverumbur", "Thiruverumbur", "திருவெறும்பூர்", "Tiruchirappalli", "திருச்சிராப்பள்ளி", 10.7790, 78.7570, 0.60, 0.26, 0.10, 0.65, 0.54),
    Ward("trz-bhel", "BHEL Township", "பிஎச்இஎல் டவுன்ஷிப்", "Tiruchirappalli", "திருச்சிராப்பள்ளி", 10.7860, 78.7490, 0.50, 0.44, 0.10, 0.55, 0.42),
    Ward("trz-navalpattu", "Navalpattu", "நவல்பட்டு", "Tiruchirappalli", "திருச்சிராப்பள்ளி", 10.7450, 78.7100, 0.44, 0.38, 0.08, 0.20, 0.38),
]

WARDS = CHENNAI + MADURAI + COIMBATORE + TRICHY
BY_ID = {w.id: w for w in WARDS}

CITIES = {}
for _w in WARDS:
    CITIES.setdefault(_w.city, {"name": _w.city, "name_ta": _w.city_ta, "wards": []})["wards"].append(_w)

LAND_COVER_NOTE = (
    "Ward land-cover profiles are indicative prototype values compiled from open "
    "reference material, not measurements. Weather is live from Open-Meteo."
)
