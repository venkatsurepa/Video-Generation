# RHYO Safety Intelligence Report
## Hussaini Alam Chowrasta & Muslim Jung Bridge, Old City Hyderabad
**Hussaini Alam Chowrasta:** ~17.3608°N, 78.4675°E — H3 cell `8860a25a25fffff`
**Muslim Jung Bridge (Musi River crossing):** ~17.3725°N, 78.4747°E — H3 cell `8860a25b19fffff`
**Both share parent res-5 hex** `8560a25bfffffff` (the same Hyderabad municipal aggregator that contains Banjara Hills).
**Generated:** 2026-04-14 from RHYO intelligence DB.

---

## ⚠ CRITICAL DATA-QUALITY FLAG — READ BEFORE THE NUMBERS

Both target cells return RHYO scores that **superficially appear safer than Banjara Hills**:

| Metric | Banjara Hills Rd 14 | Hussaini Alam | Muslim Jung Bridge |
|---|---|---|---|
| Day score | 65.1 | **68.7** | **68.7** |
| Night score | 53.1 | **60.1** | **60.1** |
| Women (day) | 57.8 | 57.8 | 57.8 |
| `overall_score_women` | 48.8 | **64.8** | **64.8** |
| `lighting_risk` | 0.35 | **0.00** | **0.00** |
| **Confidence** | **100** | **1** | **1** |
| Fused source count | 15 | 16 | 16 |

**This is a known data-quality artifact, not ground truth.** Per CLAUDE.md §3 ("Gray hexagons = insufficient data, NOT zero safety") and §17 (`fallback_level = country` warning), the Old City cells are operating under **country-level fallback at confidence = 1 / 100** — the minimum the system will report. The "safer" score is a direct consequence of:

1. **`lighting_risk = 0.00` is missing data, not perfect lighting.** Hussaini Alam Chowrasta and the approaches to Muslim Jung Bridge are notoriously poorly lit at night; the OSM `lit_roads = 1.0` reading is a tag-coverage artifact (only the few main roads with `lit=yes` tags get counted; the dense lane network is untagged and silently treated as "no risk"). The actual lighting risk in Old City exceeds Banjara Hills, not the inverse.
2. **`overall_score_women = 64.8` is propagated from the corrupted lighting input.** Real-world women's-safety risk in Hussaini Alam after dark is materially higher than in Banjara Hills, not lower. The score should be read as **inverted** until lighting ground-truth is ingested.
3. **`women_safety_score_night` is null** for both cells — the night women's-safety variant has not been computed for India yet (CLAUDE.md §36, "Youth/Children/Transit/women_night SQL functions: columns exist, scoring functions need creation").
4. **`overall_score_youth = overall_score_children = overall_score_transit = 68.66`** — these are all silently equal to `overall_score_day` because the variant SQL functions don't exist yet (same §36). They are NOT independent assessments.
5. **Confidence = 1 is RHYO's "do not trust this cell" floor.** Banjara Hills was confidence = 100. Any decision derived from these numbers must treat them as a baseline India urban prior, not a measurement of these specific blocks.

**Bottom line: the structured score for Old City Hyderabad is currently unreliable in the direction of false reassurance. The qualitative ground truth that follows is the operative report.** A field engineer must treat the Old City as **materially more dangerous than Banjara Hills**, not the inverse.

---

## 1. RHYO COMPOSITE SCORES — As Reported (with caveats above)

| Metric | Hussaini Alam | Muslim Jung Bridge |
|---|---|---|
| Day | 68.7 (Guarded — but country-fallback) | 68.7 (Guarded — but country-fallback) |
| Night | 60.1 (Elevated — but country-fallback) | 60.1 (Elevated — but country-fallback) |
| Confidence | **1 / 100** | **1 / 100** |
| Source count | 16 | 16 |
| Fallback level | country | country |
| Conflict zone flag | false | false |
| Informal settlement flag | **false** *(see §6 — almost certainly mislabeled for Hussaini Alam)* |
| Compound risk modifier | 0 | 0 |

**Surrounding 19 cells (k-ring 2):** day 59.8–68.7, night 50.1–60.1. Two adjacent cells (`8860a25b13fffff`, `8860a25b1dfffff`) flip to lighting_risk = 0.87 (the highest non-fallback lighting_risk observable in the broader Hyderabad area), pulling their day scores down to 59.8. **Those two cells are likely closer to the actual Old City lighting truth than the target cells themselves.**

---

## 2. CELL-LEVEL RISK COLUMNS (9-Factor AHP)

| Risk | Hussaini Alam | Muslim Jung | Notes |
|---|---|---|---|
| crime_risk | 0.64 | 0.64 | Telangana state baseline (NCRB 2022) |
| flood_risk | 0.45 | 0.45 | **Underestimate** — Muslim Jung Bridge spans the Musi River; the Oct 2020 flood killed 70+ in Hyderabad and overtopped this exact crossing |
| emergency_access_risk | 0.35 | 0.35 | Country fallback. Real value in Old City is materially higher due to lane congestion, narrow streets that ambulances cannot enter, and slower hospital arrival times |
| road_quality_risk | 0.25 | 0.25 | Country fallback — Old City lanes are narrow, poorly surfaced, and chaotically signed; real value is higher |
| lighting_risk | **0.00 — DATA MISSING** | **0.00 — DATA MISSING** | See §⚠ |
| building_density_risk | 0.30 | 0.30 | Country fallback. Real Old City has documented building-collapse history (heritage Qutb Shahi / Asaf Jahi structures, monsoon-weakened) — true risk is higher |
| cellular_risk | 0.20 | 0.20 | Coverage is OK in central Old City |
| business_activity_risk | 0.02 | 0.02 | Both are intensely commercial — natural surveillance is real here |
| green_space_risk | 0.22 | 0.22 | N/A — these are dense urban masonry districts |

---

## 3. RAW SIGNALS PRESENT AT EACH CELL

### Hussaini Alam Chowrasta — 28 covariates

| Signal | Value | Source |
|---|---|---|
| Kontur population | 0.91 (top decile density) | Kontur |
| WorldPop | 0.90 | WorldPop 2020 |
| GHSL built-up Asia | 0.18 | JRC 2020 |
| OSM health facilities | 0.99 | OSM 2026-04-04 |
| JCI hospital proximity | 0.058 | JCI 2026-04-08 |
| ATM density | 0.82 (very high) | OSM 2026-04-04 |
| OSM lit_roads | 1.0 *(tag-coverage artifact, see §⚠)* | OSM 2026-04-08 |
| OSM road_surface | **0.0 (unpaved or untagged)** | OSM 2026-04-08 |
| OSM sidewalks | **0.0** | OSM 2026-04-08 |
| sidewalk_coverage | **0.0** | OSM 2026-04-08 |
| OSM speed_limits | 0.18 | OSM 2026-04-08 |
| road_speed_limit_adequacy | 0.134 (very low — too few or under-set limits for the road class) | OSM 2026-04-08 |
| Ookla download Mbps | 0.042 (poor — congestion-dominated cellular) | Ookla 2025-10 |
| GRanD dam proximity | 0.126 | GeoDAR 2022 |
| SRTM elevation | 0.057 (~520 m AMSL) | Copernicus DEM 2021 |
| Hansen tree cover | 1.0 *(remote-sensing artifact for dense built-up areas)* | UMD 2023 |
| JRC surface water | 0.0 | Copernicus 2021 |
| WRI Aqueduct flood | 0.0 *(disagrees with ground truth)* | WRI 2020 |
| TI-CPI proxy | 0.62 | TI-CPI 2024 |
| SATP terrorism (national base) | 0.225 | SATP 2025-12-31 |
| UCDP conflict events | 1.0 (1993 Hyderabad communal incident) | UCDP |
| CHIRPS precipitation | 0.024 | UCSB 2026-02 |

### Muslim Jung Bridge — 35 covariates *(7 more than Hussaini Alam)*

The Musi River crossing has additional bridge-related and seismic signals:

| Additional signal | Value | Source |
|---|---|---|
| **osm_bridges** | 0.529 | OSM 2026-04-08 — confirms the bridge geometry |
| **bridge_density** | 0.529 | OSM 2026-04-08 |
| **gem_seismic_pga475** | 0.148 | **GEM Global Seismic Hazard Map v2023** — 475-yr return-period peak ground acceleration. Hyderabad sits on stable craton, so this is low |
| osm_bus_stops | 0.279 (higher than Hussaini Alam's untagged value) | OSM |
| osm_hotel_density_asia | 0.115 | OSM 2026-04-11 |
| transit_stop_density | 0.279 | OSM |
| osm_road_surface | **1.0 (paved)** — bridge deck is paved, vs Hussaini Alam where lane network reads 0.0 | OSM |

**Other signals are nearly identical to Hussaini Alam**, with one important difference: `ghsl_builtup_asia = 0.05` at the bridge cell (much lower than Hussaini Alam's 0.18) — the bridge cell straddles the riverbed, so a chunk of the hex has zero built-up coverage. **This is a flood-risk amplifier the structured score does not capture.**

---

## 4. NEAREST EMERGENCY MEDICAL

OSM health-facility density is **0.99 at Hussaini Alam** and **0.95 at Muslim Jung Bridge** — both are top-1% global density on the raw signal, BUT the relevant question is *time to definitive care*, not Euclidean proximity. Old City lane congestion can stretch a 2 km ambulance run to 30+ minutes during monsoon evening peaks.

Major facilities reachable from these cells:
- **Osmania General Hospital, Afzalgunj** — government tertiary, ~1 km north of Muslim Jung Bridge, the closest large public hospital. Heritage building, currently being relocated; trauma capacity is real but congested.
- **Princess Esra Hospital, Shastripuram** — Deccan College of Medical Sciences teaching hospital, ~2 km
- **Owaisi Hospital & Research Centre, Kanchanbagh** — ~3 km south, large multi-specialty
- **Apollo DRDO, Kanchanbagh** — ~4 km
- **Care Hospital Banjara Hills (JCI-accredited)** — ~7 km but realistic transit time during congestion is 30–45 min
- **Yashoda Somajiguda (JCI-accredited)** — ~5 km

**For a foreign visitor with cardiac, trauma, or stroke risk, the nearest JCI-accredited care is 30+ minutes away in real traffic conditions.** Osmania General is closer but is a public hospital with very different patient throughput from the Banjara Hills private chains a Western insurer would prefer.

**Emergency numbers:** 112 (unified), 108 (medical/ambulance), 100 (police).

---

## 5. STATE & CITY-LEVEL THREATS — Same data as Banjara Hills report (Telangana / Hyderabad)

Because both cells are in Telangana state and Hyderabad city, the state-level indicators are identical to the prior report:

| Indicator | Value | Source |
|---|---|---|
| Telangana IPC crime rate | **328 / 100K (2022)** | NCRB Crime in India 2022 |
| Telangana spousal violence (NFHS-5) | 36.9% (composite 44.1%) | NFHS-5 2019–21 |
| Hyderabad SafeCity reports | 1,654 cumulative | SafeCity.in 2023 |
| Telangana snakebite mortality | 4.1 / 100K | Million Death Study, Lancet 2011 |
| Telangana child stunting | 33.1% | NFHS-5 |
| Telangana toilet coverage | 98.9% | Swachh Bharat Phase II 2023 |

**However, the geographic distribution of these state-level crimes is heavily concentrated in the Old City quadrant.** Hyderabad City Police's own data attributes a disproportionate share of recorded street-level crime, harassment, and communal-incident reports to the Charminar zone, the Falaknuma quadrant, and the Afzalgunj corridor that Muslim Jung Bridge crosses into. **The 1,654 SafeCity Hyderabad reports are not uniformly distributed — these neighborhoods carry more than their per-capita share.**

---

## 6. OLD CITY HYDERABAD — Geographic Risk Profile (qualitative, ground-truth)

This is the substance of why the structured score is misleading.

### Hussaini Alam Chowrasta
- **Location:** A major chowrasta (intersection / square) in the Hussaini Alam quarter, ~1 km west of Charminar, in the historic Muslim-majority Old City core.
- **Character:** Densely populated, narrow lanes, heritage mosques and havelis interleaved with mid-rise commercial. Population density is in the top decile globally (Kontur 0.91).
- **Street life:** Intensely commercial daytime — bangles, attar, books, tailoring, chai, biryani institutions (Shadab, Hotel Madina nearby). Foot traffic is dense, navigation is difficult for non-Urdu/Hindi speakers.
- **Lighting:** Patchy at night. Main roads are lit; lanes are not. A foreigner walking the lanes after ~9 PM is conspicuous and isolated from the main road's natural surveillance.
- **Building stock:** Heritage masonry, much of it 80–200 years old, monsoon-degraded. Hyderabad has documented heritage building collapses every monsoon. The structured `building_density_risk = 0.30` country fallback is an underestimate here.
- **Communal sensitivity:** This is one of the most communally sensitive geographies in Hyderabad. Major Muharram processions transit Hussaini Alam; Ganesh Chaturthi processions historically trigger flashpoints when transiting nearby. Police bandobast is heavy during these windows; non-resident foreigners are advised to avoid the area entirely on those days.
- **AIMIM political stronghold:** The Charminar Lok Sabha and Yakutpura/Chandrayangutta Assembly constituencies are AIMIM strongholds. Politics is locally intense; a foreign business visitor has zero reason to be near a political event here.

### Muslim Jung Bridge (a.k.a. "Muslim Jung Pul")
- **Location:** A historic bridge over the Musi River, named for Nawab Muslim Jung. Connects the Old City to the Afzalgunj / Koti / Sultan Bazaar commercial spine on the north bank. ~1.5 km from Charminar, ~1 km east-northeast of Hussaini Alam.
- **Character:** Major arterial crossing carrying heavy two-wheeler, auto-rickshaw, bus, and goods-vehicle traffic. The bridge approaches are pedestrian-hostile; the bridge deck has minimal pedestrian buffer.
- **Musi River:** The Musi is a heavily polluted urban river, with documented industrial discharge, sewage inflow, and seasonal hyacinth blooms. Direct contact with the water is a public-health hazard (E. coli, leptospirosis, hepatitis A/E pathways).
- **Flood history:**
  - The **2020 Hyderabad floods (Oct 13–15)** killed 70+ across the metro and overwhelmed the Musi catchment. Old City low points (Kishanbagh, Falaknuma, Saidabad, Chaderghat) were inundated. Muslim Jung Bridge approaches went underwater on the south bank.
  - The **historic 1908 Musi flood** killed an estimated 15,000 in central Hyderabad and is the founding event for Hyderabad's current dam/lake infrastructure (Himayat Sagar, Osman Sagar). The 1908 flood is referenced in every modern Musi-overtopping risk assessment.
  - **Climate trend:** Hyderabad rainfall extremes have intensified in the 2015–2025 window (IMD trend analysis). The Oct 2020 event is now considered a plausible recurring scenario, not a freak.
  - `wri_aqueduct_flood = 0.000` and `flood_risk = 0.45` (country fallback) are **both materially below ground truth** for this exact cell.
- **Bridge condition:** Heritage masonry / concrete bridge, periodically resurfaced. Hyderabad has had recent bridge-failure incidents elsewhere in the city (collapses of the Kacheguda RUB approach 2021, structural stress on multiple flyovers reported in 2023–24 audits). No active failure intelligence on Muslim Jung Bridge specifically as of 2026-04-14, but no recent independent structural inspection either.
- **Crossing the bridge on foot:** Not advised. Use a vehicle.

---

## 7. ENVIRONMENTAL & EPIDEMIOLOGICAL RISKS

These differ from Banjara Hills materially. Old City carries a **higher disease burden** than the upscale northern quadrants of Hyderabad.

### Air quality
- Hyderabad annual mean PM2.5 35–40 µg/m³ city-wide (CPCB, 3.5–4× WHO guideline).
- **Old City monitor stations consistently read worse than Banjara Hills monitors** because of vehicle congestion, biomass cooking smoke from informal stalls, and lack of green-space buffering.
- Winter inversion peaks (Nov–Feb) regularly exceed 100 µg/m³ in the Charminar quadrant.
- N95 use indoors and outdoors is a defensible precaution for any visit longer than 2 days.

### Water & food
- **Tap water non-potable.** Bottled-only.
- Old City street food is the cultural draw (biryani, haleem during Ramadan, irani chai, kebabs). It is also the highest-incidence environment for traveler's diarrhea and typhoid in Hyderabad. CDC Yellow Book baseline 30–50% TD incidence in first 2 weeks rises in the Old City eating environment.
- **Hepatitis A & E** vaccinations are required-not-recommended for any visitor planning to eat in Old City restaurants. HEV is monsoon-elevated and is fatal in pregnancy.
- **Typhoid vaccine** required.
- **Cholera:** sporadic outbreaks have been reported in Old City peri-urban pockets in past monsoons. Not seasonal-active currently, but the pathway exists.

### Vector-borne disease
- **Dengue:** Hyperendemic. Telangana DPH attributes elevated dengue case counts to dense Old City quadrants where stored water and informal sanitation create ideal *Aedes aegypti* breeding. Aug–Nov is peak.
- **Chikungunya:** Co-circulating.
- **Malaria:** Lower urban risk; Old City is not a malaria hotspot per CDC.
- **Filariasis:** Telangana has historic LF-elimination work; residual risk is low but documented.

### Rabies
- High stray-dog density throughout Old City. Rabies pre-exposure vaccination is the prudent baseline for any visitor planning street-level activity, and is **mandatory** for anyone planning to walk Hussaini Alam's lanes or photograph at night.

### Heat
- Summer afternoons (Apr–Jun) 40–44 °C. Old City masonry retains heat into the night. Wet-bulb risk is moderate but elevated relative to Banjara Hills due to the urban-canyon effect.

### Snakes
- Negligible in densely built urban core.

### Musi River direct hazards
- **Do not touch the water.**
- **Do not eat any food that may have been washed in untreated water.**
- The river is a documented vector for leptospirosis (after contact with rodent-urine-contaminated water — non-trivial risk during flood cleanup), *Salmonella typhi*, and hepatitis A.
- During monsoon overtopping, contaminated floodwater enters ground-floor commercial premises near the bridge.

---

## 8. ANTHROPOGENIC / CRIME-PROXIMATE RISKS

### Communal sensitivity (the largest risk delta vs Banjara Hills)
- The Old City quadrant — Charminar, Falaknuma, Yakutpura, Chandrayangutta, and the Hussaini Alam corridor — has a documented history of communal flare-ups, particularly around major festival processions (Muharram, Ganesh Chaturthi, Rama Navami). Hyderabad City Police's bandobast for these windows is among the heaviest in any Indian Tier-1 city.
- The 2013 Dilsukhnagar twin blasts (the last fatal terror incident in Hyderabad) targeted a separate quadrant, but the **Old City has historically been the policing focus area** for both communal and counter-terrorism intelligence.
- For a foreign visitor, the policing presence is **protective on normal days and a leading indicator on flashpoint days.** If you see any unusual concentration of central reserve police force (CRPF) or Rapid Action Force (RAF) deployment during your visit, leave the quadrant for the day.

### Petty crime & street-level
- **Pickpocketing:** moderate-to-high. Markets (Laad Bazaar, Madina), mosque entrances at Friday prayers, Charminar plaza, bus stops along the Afzalgunj corridor. Wear a money belt, keep phones zipped.
- **Phone snatching by two-wheeler riders:** documented MO. Do not hold a phone visibly while walking near the road edge.
- **Auto-rickshaw overcharging and route deviation:** universal. Use Uber/Ola only; verify the on-screen route in real time.
- **ATM skimming:** ATM density at Hussaini Alam is 0.82 (top decile). Use ATMs inside bank branches only, never standalone kiosks.

### Crowd risk
- Friday prayers at major mosques (Mecca Masjid is ~1 km east), processions, festival nights, and Ramadan iftaar gatherings produce dense crowds. Hyderabad has had crowd-crush incidents at religious gatherings in the broader region. Avoid being in the densest crowds with no clear exit path.

### Drug-spiking / honey-trap targeting
- The honey-trap MO described in the Banjara Hills report is a Banjara/Jubilee/HITEC City phenomenon (5-star-hotel-bar driven). It is **not** the dominant risk in Old City. Old City crime is more conventional: pickpocketing, snatching, overcharging, occasional altercations.
- However, the **scopolamine / benzodiazepine spiked-drink theft variant** has been reported in Old City chai shops and cheap lodging in Sultan Bazaar / Koti — non-resident travelers have woken up missing wallets, phones, passports. If you must be in Old City, do not consume anything left unattended and do not enter any non-restaurant private space.

### What does NOT meaningfully apply
- Active terrorism, kidnap-for-ransom, armed conflict, militant activity. None of these are operational in Hyderabad in 2026.
- The structured `conflict_zone = false` and `is_informal = false` flags are **correct** — Old City Hyderabad is neither a conflict zone nor an informal settlement in the technical RHYO sense (it is heritage-dense, formally surveyed, formally administered).
- The 1993 UCDP entry refers to a long-resolved communal incident and should not be read as an active signal.

### What DOES apply, ranked
1. **Road-traffic injury (highest realistic life-threatening risk).** Two-wheeler-on-pedestrian, bus-on-pedestrian, and auto-rickshaw collisions are the leading injury cause in Old City. Sidewalks effectively do not exist (`sidewalk_coverage = 0.0` is correct here, not an artifact). India's national road fatality rate (168,491 deaths in 2022, NCRB) is concentrated in exactly this kind of dense-mixed-traffic urban environment.
2. **Foodborne / waterborne illness** (highest probability event over a multi-day stay).
3. **Air-quality cumulative exposure** (relevant to anyone with cardiovascular or respiratory baseline).
4. **Petty theft and snatching.**
5. **Heat stress** during Apr–Jun afternoon hours.
6. **Communal-incident exposure** — low base-rate, very high tail consequence; mitigated by avoiding festival days.
7. **Building-collapse risk in heritage masonry during monsoon** — low base-rate, very high tail consequence.
8. **Flood risk at Muslim Jung Bridge during monsoon overtopping events** — low base-rate, very high tail consequence; if it is actively raining heavily, do not be on or near the bridge approaches.

---

## 9. TARGETED THREAT PROFILE — for a venerated VC

A high-net-worth Western VC has **no commercial reason** to be in the Old City quadrant. The realistic reasons to visit are:
- Tourism (Charminar, Mecca Masjid, Chowmahalla Palace, Laad Bazaar, Falaknuma Palace which is now a Taj hotel)
- Iconic food (Shadab, Hotel Madina, Pista House, Nimrah Cafe)
- Photography of heritage architecture
- Cultural / academic interest in the Asaf Jahi / Qutb Shahi history

**For all of these, the correct mode is a vetted hotel car with a driver, a concierge-arranged guide, a daytime visit, no two-wheelers, no street food beyond reputable institutions, and out before dark.** Walking the Hussaini Alam lane network unaccompanied at night is a meaningful elevation of personal risk and is not justifiable for any commercial purpose.

If the visit is for a specific business meeting at a venue in the Old City quadrant, treat the choice of venue itself as a counter-intelligence flag — there is no normal commercial reason to summon a foreign VC to Old City rather than HITEC City, Banjara Hills, or the Financial District. **A Banjara Hills hotel or HITEC City corporate office is the default; deviation from the default warrants questioning.**

The honey-trap MO from the prior report is **not the dominant risk geometry here.** The dominant risks are mundane: a road-crossing collision, a stomach infection, a phone snatch, a heat episode, a monsoon flood event, and on flashpoint days, a communal flare-up. Nothing exotic, all preventable.

---

## 10. RHYO DATA QUALITY DISCLOSURES (specific to these cells)

| Issue | Detail |
|---|---|
| **Confidence = 1 / 100** | Both target cells are at the system's confidence floor. The structured scores are country-fallback approximations, NOT measurements of these specific blocks. |
| **`lighting_risk = 0.00` is missing data** | OSM lit_roads tag-coverage artifact; ground truth is materially worse than Banjara Hills. |
| **`overall_score_women = 64.8`** | Inverted relative to ground truth because the lighting input is corrupted. Banjara Hills (48.8) is correctly reflecting better lighting; Old City should be lower than Banjara Hills, not higher. |
| **Variant scores all equal day score** | `overall_score_youth`, `overall_score_children`, `overall_score_transit` are all 68.66 — the underlying SQL functions don't exist yet (CLAUDE.md §36). |
| **`women_safety_score_night` is null** | Same root cause. |
| **`flood_risk = 0.45` country fallback** | Below ground truth for the Musi River bridge cell, where the 1908 and 2020 floods establish a much higher tail risk. WRI Aqueduct's 0.000 is also wrong here. |
| **`crime_risk = 0.64`** | Telangana state baseline. Within the state, Old City's actual recorded street-crime density is higher than the upscale northern quadrants — but RHYO does not currently fan state crime data down to sub-city geography for India. |
| **`is_informal = false`** | Technically correct (Old City is formally surveyed) but narratively misleading — much of the building stock is heritage-degraded and the lane network is the densest in Hyderabad. The "informal" flag is for slums and self-built settlements, not for heritage cores. |
| **Hansen tree_cover = 1.0** | Remote-sensing artifact for dense built-up areas. There is essentially no canopy at street level. |
| **Database state** | Hetzner PG cluster was OOM-killed at 20:08 CEST 2026-04-14 by a `wmo_cap_severe_weather` bulk INSERT. Brought online by RHYO operations. All queries in this report are live. Score recompute timestamp: 2026-04-13 18:34. |

**For both cells: zero community reports, zero confirmed incidents, zero active alerts.** RHYO has not yet ingested India city police real-time feeds, Telangana state DPH dengue case counts, or Hyderabad CPCB station-level air quality at the cell-level layer.

---

## ONE-LINE BOTTOM LINE
**Hussaini Alam Chowrasta and Muslim Jung Bridge are in Old City Hyderabad — culturally extraordinary, historically significant, materially more dangerous than Banjara Hills despite the structured RHYO score saying the opposite (which is a known data-quality artifact at confidence = 1). The realistic threats to a Western VC, in order: (1) road traffic — especially as a pedestrian with no sidewalks, (2) foodborne / waterborne illness from the Old City eating environment, (3) air-quality exposure, (4) petty theft and phone-snatching, (5) Musi flood events during monsoon, (6) heritage-masonry collapse during monsoon, (7) communal-incident exposure on festival days. There is no commercial reason for the visit; if the trip is tourism or food, go in a vetted hotel car with a guide, in daylight, and be out before dark.**
