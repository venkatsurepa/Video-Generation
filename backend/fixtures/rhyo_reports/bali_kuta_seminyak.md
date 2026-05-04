# RHYO Safety Intelligence Report
## Kuta & Seminyak beach areas (Legian Street nightlife / money-changer corridor / Kuta Beach), Badung Regency, Bali, Indonesia
**Coordinates:** −8.7180°S, 115.1690°E
**H3 Cell (res 8):** target cell **not in safety_scores; see §10** | **Parent (res 5):** `8595a4c3fffffff` (244 child cells, inner south Bali)
**Generated:** 2026-05-03 from RHYO intelligence DB (Hetzner PG16, 158M-cell global grid; Indonesia subset)

---

## 1. RHYO COMPOSITE SCORES — Target cell context

The exact target cell (Kuta beach centroid at −8.7180, 115.1690) is missing from `safety_scores` — it sits at the Indian Ocean/beach edge and was excluded by a land-coverage filter. Surrounding cells in the same res-5 parent provide the operational picture.

| Metric | Value (from k-ring 2 / parent) | Band |
|---|---|---|
| Overall Day Score (k-ring avg) | **78.2 / 100** | Guarded → Clear |
| Overall Night Score (k-ring avg) | **73.5 / 100** | Guarded |
| Day score range (k-ring 3 cells) | **77.2 → 80.2** | heterogeneous (real signal) |
| Night score range (k-ring 3 cells) | 71.5 → 77.5 | heterogeneous |
| Res-5 parent (244 cells, inner south Bali): day | **76.3** | Guarded |
| Res-5 parent: night | 70.7 | Guarded |
| Confidence (parent typical) | high | — |
| Timezone | Asia/Makassar (WITA, UTC+8) | — |
| Conflict zone | false | — |
| Informal settlement | false | — |

**Reading:** Inner south Bali (the Kuta–Legian–Seminyak–Canggu axis covered by this res-5 parent) scores in the **"Guarded" band** with a relatively mild diurnal delta (~5–7 points). **The night drop is the smallest in this five-city report set after Lisbon and Istanbul** — Kuta's tourist-quarter character keeps streets lit and patrolled until late, and Seminyak is even more of a "always-on" tourism zone.

**The k-ring is only 3 cells (vs typical 19)** because Kuta sits on the Indian Ocean coast — most of the standard hexagonal ring falls in open water.

> **Important context:** the day-77 / night-72 picture **drastically understates the Kuta-night transactional-risk profile**. RHYO's composite captures aggregate safety metrics (low homicide, present hospitals, well-lit streets) but does NOT cell-resolve **drink-spiking + methanol poisoning + drug-enforcement entrapment + scooter-injury + rip-current drowning + Mt. Agung/Batur volcanic disruption** — all of which are documented Kuta-specific risks at multiples above the country baseline. See §7–§9 for the operational picture.

### What's in the parent res-5 average (244 cells)

- **crime_risk = 0.10** (very low — Indonesia national homicide 4.1/100K with Bali specifically much lower; tourist-targeted homicide effectively zero)
- **flood_risk = 0.45** (moderate — Bali wet-season flash flooding documented; Kuta low-lying)
- **emergency_access_risk = 0.97** (apparent contradiction — Kuta has dense health POIs; this is a national-physician-density 0.52/1000 rollup override — see §2 and §10)
- **lighting_risk = 0.29** (low — Kuta tourist core well-lit; OSM lit roads = 1.00 at cell)

---

## 2. CELL-LEVEL RISK FACTORS (9-Factor AHP — read from parent context, target cell missing)

| Risk Column | Parent Value | Read |
|---|---|---|
| **crime_risk** | 0.10 | **Very low** — Bali has the lowest tourist-violence crime rate of the five cities in this report; predominant patterns are non-violent theft and scams |
| **flood_risk** | 0.45 | Moderate — Kuta is low-lying coastal; wet-season (Dec–Feb) flash flooding documented; Tabanan/Denpasar coastal subsidence |
| **emergency_access_risk** | **0.97** | Reads "Very High Risk" but **conflicts with cell-level data**: `id_osm_police_stations = 0.97` (very close), `healthsites_proximity = 0.012` (top 1%), `osm_pharmacy_access = 0.77` (high). The 0.97 risk reflects Indonesia's national physician shortage (0.52/1000, WB 2023 — lowest in this report set). On-the-ground Kuta has BIMC, Siloam, and Kasih Ibu hospitals within minutes; **JCI-grade care requires emergency air evacuation to Singapore for highest-acuity cases**. |
| **road_quality_risk** | (not explicit) | Bali roads are paved (`osm_road_surface = 1.0`) but **scooter-dominant traffic mix is the highest-fatality vector** for tourists in Indonesia — see §6 road safety |
| **lighting_risk** | 0.29 | Low — Kuta tourist strip is well-lit (`osm_lit_roads = 1.0`); back-gang sois (Bemo Corner, Poppies Lane areas) less so |
| **building_density_risk** | low | Kuta hotel density `osm_hotel_density_asia = 0.58` (top quartile) |
| **cellular_risk** | low | Telkomsel / XL / Indosat coverage strong on the south Bali axis |
| **business_activity_risk** | low | Saturated commercial = natural surveillance |
| **green_space_risk** | low | Beach access; minimal urban green other than Bali Bombing Memorial garden |

---

## 3. RAW SIGNALS PRESENT AT TARGET CELL (26 covariates — rich despite missing safety_scores row)

| Signal | Value | Source | Date |
|---|---|---|---|
| OSM road surface | **1.00 (fully paved)** | OSM/Overpass | 2026-04-08 |
| OSM sidewalks | **1.00 (full coverage)** | OSM/Overpass | 2026-04-08 |
| Sidewalk coverage derived | **1.00** | OSM derived | 2026-04-08 |
| OSM lit roads | **1.00 (top of distribution)** | OSM/Overpass | 2026-04-08 |
| **ID OSM police stations** | **0.97 (very close — Kuta has dedicated tourism police)** | OSM/Overpass | 2026-04-04 |
| OSM pharmacy access | **0.77 (high)** | OpenStreetMap | 2026-04-04 |
| WorldPop population | 0.70 | WorldPop | 2020 |
| OSM bridges | 0.68 | OSM/Overpass | 2026-04-08 |
| Bridge density derived | 0.68 | OSM/Overpass | 2026-04-08 |
| **OSM hotel density (Asia)** | **0.58 (top quartile — Kuta is hotel core)** | OSM | 2026-04-11 |
| OSM ATM density | 0.54 | OSM | 2026-04-04 |
| OSM bank/ATM density | 0.54 | OSM | 2026-04-04 |
| OSM bus stops | 0.41 | OSM/Overpass | 2026-04-08 |
| Transit stop density | 0.41 | OSM | 2026-04-08 |
| OSM toilets | 0.32 | OSM/Overpass | 2026-04-08 |
| OSM crossings | 0.24 (moderate) | OSM/Overpass | 2026-04-08 |
| Crosswalk density | 0.24 | OSM/Overpass | 2026-04-08 |
| HDX health facilities (ID) | 0.23 | HDX/healthsites.io | 2026-04-11 |
| OSM pharmacy density (Asia) | 0.15 | OSM | 2026-04-11 |
| **Health-sites proximity** | **0.012 (top 1%)** | OSM/Overpass | 2026-04-08 |
| GESLA extreme sea level | 0.02 (low) | GESLA-4 | 2026-04-07 |
| OSM lanes | 0.0 | OSM | 2026-04-08 |
| OSM road width | 0.0 (cell-level OSM gap) | OSM | 2026-04-08 |
| OSM speed limits tag | 0.0 | OSM | 2026-04-08 |
| Road speed-limit adequacy | 0.0 | OSM derived | 2026-04-08 |
| **UCDP conflict events** | **1.00 — 2002-10-12** | UCDP | **2002-10-12 — the Bali Bombings (Sari Club / Paddy's Bar, Legian Street)** |

**The UCDP 2002-10-12 row is the most historically loaded covariate in this report set** — it is the geo-tagged record of the **2002 Bali bombings** (202 dead, mostly Australian and Indonesian tourists), centered on Sari Club and Paddy's Bar on Legian Street, ~600 m from the target coordinate. The Bali Bombing Memorial (Ground Zero Monument) stands on the Sari Club site.

**Most actionable cell-level signal:** `id_osm_police_stations = 0.97` confirms the dense police presence — Kuta-specific has the **POLDA Bali Tourism Police office on Jl. Pantai Kuta**, with multilingual officers and the PolisiKu app.

---

## 4. NEAREST EMERGENCY MEDICAL — Verified hospital proximity

Health-sites proximity at this cell = **0.012 (top 1%)**. Major south Bali facilities within ~10 km of Kuta:

- **BIMC Hospital Kuta** (Jl. Bypass Ngurah Rai 100X, Kuta) — private international, ~2 km, **24/7 ER + foreigner-focused**, cash/card direct billing
- **Siloam Hospital Bali** (Jl. Sunset Road 818, Kuta) — private chain tertiary, ~3 km, JCI-affiliated practices
- **BIMC Hospital Nusa Dua** (Kawasan Pariwisata Nusa Dua) — private international, ~15 km
- **Kasih Ibu Hospital Denpasar** (Jl. Teuku Umar) — private tertiary, ~7 km
- **RSUP Sanglah / Prof. Dr. I.G.N.G. Ngoerah General Hospital** (Jl. Diponegoro, Denpasar) — **public flagship, **only Bali hospital with full-spectrum tertiary including neurosurgery**, ~10 km
- **Bali Mandara Hospital** (public, Sanur) — ~12 km

**Critical:** Bali has **NO JCI-accredited hospital on the island** as of this report period (Q1 2026). For high-acuity cases (severe burns, complex polytrauma, pediatric ICU), **air evacuation to Singapore (Mount Elizabeth, Raffles, NUH) is the standard pathway**, run by services like International SOS, AEA International, MedicAir Asia. **Travel medical insurance with evacuation coverage is essential** — Bali-specific medical evacuations to Singapore typically cost USD 50,000–150,000.

JCI-grade in-Bali equivalents (BIMC, Siloam) handle most acute presentations: motorbike trauma, jellyfish/coral injuries, food poisoning, dengue, drug overdose, drowning resuscitation. **Drowning recovery and methanol-poisoning treatment at BIMC/Siloam are routine** — they have institutional muscle memory.

*Sources: OSM/Overpass (2026-04-08), HDX healthsites.io Indonesia (2026-04-11), id_osm_police_stations (2026-04-04).*

**Indonesian emergency numbers:**
- **112** — Unified emergency (police, fire, ambulance) — operational nationally since 2016
- **110** — Police (still active legacy)
- **118 / 119** — Ambulance / Medical (legacy; varies by region)
- **113** — Fire
- **115** — SAR (Basarnas — for water/mountain rescue)
- **POLDA Bali Tourism Police** (Jl. Pantai Kuta) — multilingual; THE first stop for foreigners
- **PolisiKu app** — official Polri app with English-capable dispatch
- **International SOS Bali alarm center** — 24/7 medical evacuation coordination

---

## 5. CITY & DISTRICT-LEVEL THREATS (Kuta / Legian / Seminyak — Badung Regency, Bali)

| Indicator | Value | Source |
|---|---|---|
| **Wikivoyage Indonesia safety composite** | **45.6 / 100 (caution — lowest in this report set)** | RHYO text-extraction pipeline 2026-04 |
| **WEF TTDI Safety pillar (Indonesia)** | 4.9 / 7.0 | WEF 2024 |
| **WEF TTDI Overall** | 4.37 / 7.0 | WEF 2024 |
| **Indonesia homicide rate** | **4.1 / 100K (WHO 2021)** — Bali specifically much lower (~0.5/100K, BPS) | WHO GHO |
| **Indonesia OWID homicide** | 0.30 / 100K | OWID |
| **Indonesia UNODC kidnapping** | 0.53 / 100K (low) | UNODC-CTS |
| **Bali tourist arrivals (2024 estimate)** | ~5.3M international | BPS Bali (separate from this DB) |
| **2002 Bali bombings** | 202 dead at Sari Club / Paddy's Bar, Legian | UCDP 2002-10-12 (cell-level row) |

Kuta and Seminyak sit in **Badung Regency** on the south coast of Bali. **Kuta** is the older, denser, more backpacker-and-Australian-charter-flight zone — Legian Street and Poppies Lane are the nightlife corridors. **Seminyak** (3 km north) is the boutique/upmarket evolution — beach clubs (Potato Head, Ku De Ta, La Plancha), villa rentals, fine dining. **Canggu** (further north) is the digital-nomad / surfer evolution. These four zones together dominate Bali's south-coast tourism economy.

---

## 6. NATIONAL-LEVEL CONTEXT (Indonesia — selected indicators)

### Travel advisories (state actor sources)
| Source | Level | Score |
|---|---|---|
| **US State Department** | **Level 2 — Exercise Increased Caution** | 0.35 (LOW) |
| **US State Dept threat composite** | 0.35 (LOW) | info |
| **UK FCDO** | "1D / 5W / 3C" composite | 0.80 (warning — driven by Papua, North Maluku, Aceh, Sulawesi) |
| **German Auswärtiges Amt** | **No travel warning** | 0.0 |
| **Canada (travel.gc.ca)** | **Level 1 / 4** (safest) | 0.25 |
| **CDC (US health)** | 3 active health notices | 0.30 |

> *None of the major foreign-ministry advisories single out Bali for elevated caution. The "do not travel" zones are exclusively **Papua, parts of Maluku, central Sulawesi (post-MIT-Poso conflict tail), and Aceh strict-Sharia jurisdiction**. Bali's risk profile is fundamentally different — tourist-targeted petty crime, road-traffic injury, drug-enforcement, drowning, and natural hazards.*

### Crime / homicide / violence (national)
- **WHO intentional homicide:** **4.1 / 100K (2021)** — Bali specifically <1/100K (BPS Bali)
- **OWID homicide:** 0.30 / 100K (very low — newer methodology)
- **UNODC kidnapping:** 0.53 / 100K
- **OWID conflict deaths 2025:** (not in current snapshot — historic Aceh / East Timor / sectarian flares)
- **OWID terrorism deaths 2021:** (not in snapshot but **2002 Bali bombings were the deadliest tourist-targeted attack in 21st-century Asia until 2019 Sri Lanka Easter attacks**)
- **Mass Mobilization protest events:** 153

### Governance & rule of law
- **Freedom House Status:** **Partly Free (Status=2)** — Civil Liberties=4/7 (caution), Political Rights=2/7 (info)
- **WJP Order and Security:** 0.69 (caution)
- **WJP Criminal Justice:** 0.395 (warning)
- **TI Corruption Perceptions:** ~38/100 (warning)
- **WB Control of Corruption:** percentile 37% (warning)
- **WB Voice & Accountability:** percentile 54% (caution)
- **PTS Political Terror:** (not explicit in snapshot)
- **Cline Center coups:** 7 historical, 1 post-2000 (1965 Suharto-era; 1998 Reformasi was political transition, not coup)
- **INFORM Risk Index:** **4.5 / 10 (warning)**
- **INFORM Hazard Exposure:** **7.1 / 10 (danger — Ring of Fire)**
- **INFORM Severity Index:** 5.6 (warning — Papua humanitarian situation)
- **Global Peace Index:** **1.857 (Indonesia ranks ~46/163, comfortably mid-tier)**

### Public health
- **Life expectancy:** 71.3 yrs (WB) — caution
- **WHO PM2.5 annual:** 19.3 µg/m³ (warning) — Bali-specific lower (~10–15) outside burning season
- **WB current PM2.5:** 17.9 µg/m³
- **Adult HIV prevalence:** 0.4%
- **WHO TB incidence:** **312 / 100K (warning — among highest globally)** — Indonesia carries one of the world's largest TB burdens
- **WHO malaria incidence:** 2.2/1000 at-risk pop; **Bali is malaria-free**, but Papua/eastern Indonesia is high-risk
- **WHO DPT3 immunization:** 78% (caution — declining post-COVID disruption)
- **WHO UHC service coverage:** 66/100 (caution)
- **WB physicians per 1000:** **0.52 (warning — lowest in this report set)**
- **JMP basic water service:** 58.5% (warning — national; Bali tourist zones much higher)
- **JMP safely-managed sanitation:** 88.2%
- **WHO drowning DALYs:** **118 / 100K (warning)** — Indonesia has very high drowning mortality (water-bound archipelago)
- **WHO alcohol per capita:** 0.085 L (very low — Muslim-majority national average; Bali Hindu-majority drinks more)
- **OpenDengue 2024 cases:** **210,644 (Indonesia)** — Bali is hyperendemic; rainy season peaks
- **WB GDP per capita:** **$4,925 (lowest in this report set)** — relevant for cost-of-living context but not directly for safety

### Hazards (Indonesia is the highest-hazard country in this report set)
- **EM-DAT natural disasters:** **421 events with 190,912 deaths** — by far the highest in this set
  - **2004 Indian Ocean tsunami:** ~167,000 dead in Aceh
  - 1908 Krakatoa eruption (~36,000 dead)
  - 2018 Sulawesi (Palu) earthquake + tsunami (~4,300 dead)
  - 2018 Lombok earthquakes (~560 dead) — felt in Bali
  - Multiple Mt. Merapi (Java) and Mt. Sinabung eruptions
- **GDACS active events:** 3 (caution — earthquake-class)
- **USGS earthquake max mag (recent):** **7.4 (warning)**
- **WRI Aqueduct riverine flood:** 4.16 / 5 (high)
- **WRI Aqueduct water stress:** 2.67 / 5
- **WHO snakebite venomous species:** 28 (warning)
- **GBIF saltwater crocodile records:** 284 (Indonesia — concentrated in Kalimantan / Papua mangroves; **not Bali**)
- **GBIF mugger crocodile:** 2 records
- **WFSA ferry fatalities:** **2,281 (2000–2015) — highest globally** — Indonesian ferry safety is a documented chronic issue (Lebaran-period overloading, weather override)
- **Volcanic activity (Bali-specific):** **Mt. Agung (3,031 m)** in northeast Bali had major eruption sequence Nov 2017 – Jun 2019, closing Ngurah Rai airport multiple times; **Mt. Batur (1,717 m)** is active and frequently climbed by tourists at sunrise (occasional deaths from misadventure, not eruption)
- **Tsunami risk (Bali-specific):** Bali sits in the Indonesian island arc; Indian Ocean subduction zone south of the island. **Unlike Aceh 2004, Bali's south coast (Kuta) faces Australian plate subduction and has shorter tsunami arrival times** (10–30 min) for any near-field event. **No siren network** equivalent to Japan/Chile in 2026.

### Social & rights (Indonesia operates a complex secular-Sharia overlay)
- **Equaldex equality index:** **0.12 (very low — 4th-lowest globally for tracked countries)**
- **Equaldex legal index:** 0.13 (low) — same-sex relations criminalized in Aceh (Sharia jurisdiction); 2023 KUHP made sex outside marriage illegal nationally (cohabitation between unmarried adults technically prosecutable on complaint by family member)
- **Equaldex public opinion:** 0.11 (very low)
- **WBL women's safety legal score:** 43.75 (caution)
- **TIP Report tier:** **Tier 2** (caution) — Indonesia is destination + transit + source for trafficking
- **AMAR at-risk minorities:** 4 groups
- **Drug law:** **Indonesia maintains the death penalty for trafficking and has executed foreign nationals** (Bali Nine 2015: Andrew Chan and Myuran Sukumaran; multiple others); cannabis is criminalized (jail for personal use); **HRI death-penalty-for-drugs score 0.85 (danger — high application)**
- **2023 KUHP (criminal code revision):** sex outside marriage criminalized (effective Jan 2026); cohabitation criminalized; insulting the President; blasphemy. **Foreigners are explicitly subject** but enforcement against tourists remains rare; the law is more often used in domestic political contexts.

### Surveillance & legal-strict regime (relevant for tourists)
- **Comparitech CCTV density:** 2 cameras/1K (low coverage)
- **Comparitech censorship:** 40/100 (danger) — porn/gambling sites blocked nationally; some social media periodically restricted
- **Comparitech SIM registration:** **mandatory**
- **Comparitech biometric:** 11/25 (danger)
- **Wiki drug legality:** **1.00 (danger — death penalty for trafficking)**

### Road safety
- **WHO road traffic deaths:** 11.3 / 100K (info, but **scooter-tourist fatality is a Bali-specific over-represented vector**)
- **WB road mortality:** 11.3 / 100K
- **OICA fleet density:** 485 vehicles/1000 (high — predominantly scooters/motorbikes)
- **Driving side:** **left** (UK convention — relevant for visitors from US/EU/MX)
- **Scooter rental** is the dominant tourist transport in Bali; Australian/UK consular casualty data shows **Bali is the leading destination for scooter-related foreign tourist deaths in Southeast Asia after Thailand**

---

## 7. ENVIRONMENTAL & EPIDEMIOLOGICAL RISKS — Bali-specific

### Drowning at Kuta Beach (the highest-frequency catastrophic risk)
- **Kuta Beach has powerful longshore and rip currents** — Indian Ocean swell hits a steeply shelving sandy beach with no offshore reef breaks (unlike Uluwatu)
- **Multiple tourist drowning deaths annually** — typical victims are non-swimmer or moderate-swimmer adults caught in rip currents
- **Lifeguards present (Balawista — Bali Beach Watch Authority)** but NOT continuous along the entire Kuta–Legian–Seminyak strip
- **Mitigation:** swim only between flags (red/yellow); never alone; never intoxicated; understand rip current escape (parallel to shore, not against current); evening surf conditions deteriorate fast

### Surfing-related injury (Uluwatu / Padang Padang / Bingin / Keramas)
- Reef breaks have shallow coral; injuries from coral abrasion + secondary infection are routine ER presentations at BIMC
- Surfing fatalities documented (Padang Padang 2018, Uluwatu multiple)

### Volcano risk (Mt. Agung & Mt. Batur)
- **Mt. Agung (3,031 m, NE Bali)** — major eruption sequence 2017–2019; closed Ngurah Rai airport multiple times; ash plumes affected south Bali tourism. Currently low-level activity (PVMBG monitoring level 2 / "Waspada" / "Be alert"). Climbing closed periodically.
- **Mt. Batur (1,717 m)** — active strato-volcano; Trekkers go pre-dawn for sunrise; misadventure deaths every few years (falls, hypothermia, dehydration). Climbing is allowed but only with licensed local guides (HPPGB).
- **Tsunami:** Bali south coast faces the Indian Ocean Sunda subduction zone. **A near-field megathrust event would give 10–30 min warning**; Indonesian InaTEWS tsunami warning system has limited siren coverage on Bali (Kuta has minimal warning infrastructure).

### Earthquakes
- **Bali sits in the Indonesian Banda Arc** — frequent M5–6 events; M7+ rare but devastating (e.g., 1815 Bali earthquake)
- **2018 Lombok earthquakes (M6.4, M7.0, M6.9, M6.3)** were felt strongly in Bali; minor damage in north Bali, no Kuta damage
- BMKG (Indonesian meteorology agency) maintains earthquake/tsunami alerting; SMS / app available

### Vector-borne disease
- **Dengue:** **HYPERENDEMIC in Bali** — 210,644 confirmed cases nationally in 2024; Bali specifically has year-round transmission with peaks in wet season (Nov–Apr). *Aedes aegypti* breeds in temple offering vessels, swimming pool overflow, AC drip, paddy fields. **Dengue is the most likely infectious disease a Kuta visitor will catch.**
- **Chikungunya:** Co-circulating
- **Japanese Encephalitis:** Endemic in rural Bali (paddy fields); vaccine recommended for stays >4 weeks or rural itinerary
- **Malaria:** **Bali is malaria-free** (CDC: prophylaxis NOT recommended for Bali specifically)
- **Rabies:** **Bali has had ongoing rabies outbreak since 2008** — significant stray dog population, multiple tourist deaths recorded over the past 15 years. **Pre-exposure rabies vaccination is strongly recommended for all Bali visitors**, even short stays. Post-exposure prophylaxis is available at BIMC and Siloam but supply can be intermittent during outbreak peaks.

### "Bali Belly" (travelers' diarrhea) and methanol poisoning
- **Travelers' diarrhea ("Bali Belly")** baseline 40–60% incidence in first 2 weeks (CDC Yellow Book) — *E. coli*, *Salmonella*, *Vibrio*, occasional *Giardia*
- **Tap water NOT potable** — bottled or filtered only; ice in established hotels/restaurants generally filtered, in cheap warungs not always
- **METHANOL POISONING from "oplosan" (illicit homemade arak / palm wine adulterated with methanol):** **multiple Australian and Western tourist deaths documented over the past decade** (2009 Lombok 25 dead, 2017 Lombok 4 dead, 2018 Sumbawa, recurring single-tourist deaths in Bali). **Avoid arak / palm wine / unbranded spirits; stick to sealed-bottle Bintang beer or branded imported spirits with intact tax stamps.** Symptoms (vision change, severe acidosis) appear 12–24 hr after consumption — **immediate ER if suspected; methanol poisoning is treatable with ethanol or fomepizole if caught early**.

### Air quality
- Kuta annual mean PM2.5: ~10–15 µg/m³ baseline (Bali coastal)
- **Burning season (kemarau, Aug–Oct):** Smoke from Sumatra/Kalimantan agricultural fires can drift to Bali — PM2.5 elevated to 50–100 µg/m³ during major haze events (2015, 2019)
- **Volcanic ash:** episodic during Mt. Agung activity
- General: vastly better than Jakarta; comparable to Mediterranean coastal

### Heat / sun
- Equatorial coastal: 28–32 °C year-round, humidity 70–85%
- **UV index 11+ year-round** — sunburn risk extreme; reef-safe sunscreen mandatory
- Wet-bulb risk: moderate (humidity-driven, not raw-temperature-driven)

### Stings, bites, and water hazards
- **Box jellyfish:** present in Indonesian waters — rare but documented Bali stings
- **Stonefish, sea urchins, fire coral:** routine swimmer/snorkeler injuries
- **Saltwater crocodile:** range does NOT include Bali; risk on Komodo / Flores / Kalimantan only
- **Stray dogs:** see rabies above
- **Macaques (Ubud Monkey Forest, Uluwatu):** routine biting incidents; rabies risk; do not feed

---

## 8. ANTHROPOGENIC / CRIME-PROXIMATE RISKS

### What does NOT meaningfully apply to Kuta/Seminyak:
- **Insurgency / violent territorial conflict** — Bali has no insurgent presence; Indonesia's separatist conflicts are in Papua (West Papua / OPM) and historically Aceh (resolved 2005)
- **Active terrorism (current)** — Jemaah Islamiyah perpetrated the 2002 (Sari Club / Paddy's, Legian) and 2005 (Jimbaran beach, Kuta Square) attacks. **Since 2009 (Marriott/Ritz-Carlton Jakarta) Indonesian counter-terrorism (Densus 88) has been highly effective**; major attack frequency has collapsed. Current foreign-ministry advisories rate Bali at standard-vigilance only.
- **Cartel-territorial violence** — not a feature
- **Active conflict zone** — flag = false
- **Kidnap-for-ransom** — effectively zero
- **Informal settlement** — flag = false
- **Civil unrest disrupting tourist quarter** — Bali's Hindu-majority demographic and tourism economy keep protest dynamics very different from Jakarta/Surabaya

### What DOES apply (the operative threat list for Kuta/Seminyak):

| Risk | Notes |
|---|---|
| **Money changer scam** | **THE Kuta-corridor signature scam.** Pattern: small back-alley money changers ("Authorized" but unlicensed) advertise rates 3–5% better than banks/PVA. Operating model: cashier counts cash slowly, palms 2–4 large notes during the hand-over, recounts shows shortfall, "apologizes" and adds back fewer than removed. Net: tourist loses 10–25%. **Use only PT Central Kuta Money Exchange, BMC Money Changer, or bank ATMs (BCA/Mandiri/BNI inside branches).** Look for ".com.id" website on signage; reject sliding doors / curtained booths. |
| **Drink spiking on Legian Street** | Documented at Sky Garden, Bounty, Engine Room, Paddy's Reloaded, La Favela. Operating model: scopolamine/benzo in poured drink; victim wakes hours later with phone/wallet/electronics gone. **Never accept poured drinks; stay in groups; carry from bar to table.** |
| **Methanol poisoning ("oplosan")** | See §7 — kills tourists every few years. Avoid arak, jungle juice, unbranded spirits. |
| **Drug-enforcement entrapment** | **Indonesia's drug enforcement is among the world's harshest.** Death penalty has been applied to foreign nationals (Bali Nine 2015). Cannabis possession = jail (no decriminalization). **Documented operating pattern**: dealer offers tourist drugs → undercover police arrest → bribe extraction; if bribe refused, prosecution at 4+ years. **Refuse all drug offers; do NOT accept "samples" from strangers; do not buy from villa cleaners or scooter dealers.** |
| **Scooter rental injury** | **The single highest-fatality vector for Western tourists in Bali.** Operating context: poor road surface in back lanes, no tourist licensing enforcement, alcohol-rider mix, helmet noncompliance, tropical rain → wet roads. **Australian consular data** consistently lists Bali scooter accidents among top-2 causes of foreign-tourist fatalities. **If you must ride: full-face helmet, defensive driving, no alcohol, no rain riding, valid international motorcycle permit (legally required, often unenforced).** Travel insurance often **excludes scooter accidents without an Indonesian motorcycle license**. |
| **Taxi / ride-share fare gouging** | Predatory taxi mafia historically blocked Grab/Gojek pickups in tourist zones. **Use Bluebird taxis (the only reliable metered chain) or Grab/Gojek (now broadly accepted in Kuta/Seminyak — confirm pickup point off main strip if necessary).** |
| **ATM card-skimming** | Documented at stand-alone ATMs along Legian/Sunset Road; use bank-branch ATMs (BCA, Mandiri, BNI). Cover PIN. |
| **Petty theft from villa / hotel** | Less common in branded hotels; routine in informal-villa rentals where staff have unsupervised access. Use safe; do not leave passport / cash visible. |
| **Bag-snatch from scooter** | Documented — pillion grabs bag from sidewalk pedestrian. Cross-body bag inside layer. |
| **Surf-board / surf-school overcharging** | Common; agree price before paddle out. |
| **Counterfeit Bintang beer / branded spirits** | Documented; refilled bottles. Inspect tax stamp; if seal broken, refuse. |
| **2023 KUHP risk (sex outside marriage / cohabitation)** | New criminal code took effect Jan 2026. Prosecutable on third-party complaint only (parent / spouse). **Foreigner enforcement has been minimal so far** but the legal exposure exists. Hotels in Kuta/Seminyak generally do NOT enforce; villa rentals vary. |
| **LGBTQ+ visibility risk** | Bali is the most LGBTQ+-tolerant region in Indonesia in practice (heavy Western tourist economy) — **but legal regime is conservative**. Aceh applies Sharia (does not affect Bali). 2023 KUHP technically applies. **Public displays of affection are not advised; Pride events have been disrupted.** |
| **Earthquake / tsunami** | See §7. Real, not currently active alert. |
| **Volcanic disruption** | Mt. Agung activity has closed Ngurah Rai airport multiple times since 2017. Travel insurance with "ash cloud" coverage advised. |
| **Stray dog rabies** | Standing risk; pre-exposure vaccine recommended. |

---

## 9. TARGETED THREAT PROFILE — for a Western solo tourist in Kuta/Seminyak

The risk delta between this individual and a generic Balinese is concentrated in six categories:

1. **Drowning at Kuta Beach** — annualized highest catastrophic risk for non-swimmer/moderate-swimmer tourists. Mitigation: swim between flags only; never alone; never intoxicated; understand rip current escape.
2. **Scooter-rental injury** — highest non-marine catastrophic risk. Mitigation: **don't rent unless you have prior motorcycle experience and a valid international motorcycle permit**; if you do — full-face helmet, no alcohol, no rain.
3. **Methanol poisoning + drink-spiking** — paired nightlife risks. Mitigation: avoid arak/palm wine/unbranded spirits entirely; stick to sealed Bintang or branded spirits; never accept poured drinks; carry from bar to table.
4. **Drug-enforcement trap** — life-altering risk (long prison sentence; death penalty for trafficking). Mitigation: refuse all drug offers; do not buy from villa cleaners, scooter dealers, or "friendly" strangers.
5. **Money-changer scam** — financial damage, occasional escalation. Mitigation: use PT Central Kuta Money Exchange or BMC; bank ATMs in branches; reject curtained / sliding-door booths.
6. **Earthquake/tsunami situational awareness** — real risk; have a evacuation plan from your accommodation; install BMKG app.

**There is no credible current-tense terrorism, kidnap-for-ransom, or political-violence risk to a tourist in Kuta/Seminyak under normal circumstances.** Indonesian counter-terrorism has been highly effective since 2009; the 2002 Bali bombings were a watershed event that triggered structural change in regional CT cooperation. The realistic life-threatening incidents are, in descending order:

1. Drowning at Kuta Beach (rip current, intoxicated swimming)
2. Scooter rental collision
3. Methanol poisoning from oplosan
4. Tsunami (low annualized, very high consequence on south Bali coast)
5. Drug-enforcement criminal-system trap (life-altering legal exposure)
6. Drink-spiking → assault / theft / fall injury
7. Volcanic ash inhalation / airport closure during Mt. Agung event
8. Dengue (seasonal; rarely fatal in fit adults but routine ER)
9. Rabies via stray dog bite
10. Cardiac event aggravated by heat / dehydration / alcohol

---

## 10. RHYO DATA QUALITY DISCLOSURES

- **Target Kuta cell is missing from `intelligence.safety_scores`** — sits at the Indian Ocean / beach edge; excluded by land-coverage filter, similar to the Lisbon Alfama riverfront pattern. **The cell IS present in `covariate_layers` with 26 covariates** — the cell-resolved signal is rich and usable.
- **K-ring 2 has only 3 cells (vs typical 19)** — most of the standard hexagonal ring falls in the Indian Ocean.
- **Res-5 parent (244 cells, inner south Bali) provides the operational rollup**: day=76.3 / night=70.7, crime=0.10, flood=0.45, lighting=0.29, emergency=0.97.
- **`emergency_access_risk = 0.97` is again misleading at the cell level** — same pattern as Bangkok Sukhumvit. Cell-level data shows `id_osm_police_stations = 0.97` (very close), `healthsites_proximity = 0.012` (top 1%), `osm_pharmacy_access = 0.77` (high). The 0.97 risk reflects Indonesia's national physician density 0.52/1000 (the lowest in this report set). On the ground, BIMC and Siloam Kuta are excellent for routine acute presentations; **highest-acuity cases require Singapore air evacuation** because Bali has NO JCI-accredited hospital.
- **`UCDP conflict events = 1.00 for 2002-10-12`** — this is the historic Bali Bombings record, geo-tagged to the cell containing Sari Club / Paddy's Bar on Legian Street. It is a real historic incident, NOT current-tense conflict signal — kept for transparency, similar to the Hyderabad 1993 and Istanbul 1991 patterns.
- **Wikivoyage Indonesia safety score 45.6** is the lowest in this report set — and it is **misleadingly low** for Bali specifically. The keyword extractor reads Indonesia's article (which discusses Papua, drug law, methanol, scooters) and applies caution-band; Bali's actual operational safety profile is closer to a Mediterranean tourist island modulo natural-hazard exposure.
- **Day-night delta is the smallest after Lisbon and Istanbul (~5–7 points)** — but this UNDERSTATES night-specific risk because RHYO does NOT cell-resolve drink-spiking, methanol poisoning, drug-enforcement, scooter intoxication, or rip-current intoxicated-swimming. Treat the headline night score as a structural-baseline conservative estimate; the §7–§9 narrative is the operational picture.
- **Indonesia's natural-hazard exposure (190,912 EM-DAT deaths from 421 events) is the highest in this report set**, dominated by 2004 Indian Ocean tsunami casualties in Aceh (not Bali). Bali's specific exposure is dominated by Mt. Agung volcanic activity, regional earthquakes (e.g., 2018 Lombok), and Indian Ocean tsunami latent risk.
- **2023 KUHP (criminal code revision) and ongoing rabies outbreak (since 2008)** are NOT in the cell-level layer and are reported here from Indonesian government and consular sources for completeness.
- **The `hri_death_penalty_drugs = 0.85 (danger — high application)` flag is operationally critical** — Indonesia has executed foreign nationals for drug trafficking within the past decade (Bali Nine 2015). This is one of the few advisory flags in this report set with documented direct-tourist fatal consequence.
- **Database state:** Hetzner PG cluster online; Indonesia coverage substantial; ~410 country indicators on file.
- **Sources cited inline.** Verifiable via: WHO GHO, World Bank WDI/WGI, UNODC, EM-DAT/CRED, USGS, BMKG, OSM/Overpass, HDX healthsites.io Indonesia, JCI directory (confirms zero JCI-accredited Bali hospitals), GESLA-4, UCDP GED (incl. 2002-10-12 Bali Bombings record), US State Dept, UK FCDO, German AA, Canada travel.gc.ca, CDC, INFORM/HDX, NTI GHSI, WEF TTDI, Wikivoyage, Comparitech, Equaldex, WBL 2026, Freedom House, Polity5, Cline Center, Mass Mobilization Project, HRI Global Overview 2024, Wiki/UNODC drug-legality dataset, Global Peace Index 2024, OpenDengue, WFSA ferry safety, Australian DFAT consular casualty data, Inside Airbnb.

---

## ONE-LINE BOTTOM LINE
**Kuta/Seminyak sits inside Indonesia's "Guarded" tourism-zone baseline with a structurally low headline crime score (0.10) but documented life-threatening tourist risks NOT reflected in the composite, where the realistic threats to a Western solo tourist's life are, in order: (1) drowning at Kuta Beach rip currents (esp. intoxicated, esp. at dusk), (2) scooter-rental collision, (3) methanol poisoning from arak / oplosan, (4) tsunami (low annualized, 10–30 min warning if it strikes), (5) drug-enforcement entrapment (long prison sentence; death penalty for trafficking), (6) drink-spiking on Legian Street, (7) dengue and rabies in the background — NOT current-tense terrorism (despite the 2002 Bali Bombings memorial 600 m from this cell), NOT kidnapping, NOT political violence; call 112 or visit POLDA Bali Tourism Police on Jl. Pantai Kuta for foreigner incidents; ensure travel insurance includes Singapore medical evacuation.**
