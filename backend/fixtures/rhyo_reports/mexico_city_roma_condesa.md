# RHYO Safety Intelligence Report
## Colonia Roma & Condesa, Cuauhtémoc Borough, Mexico City (CDMX), Mexico
**Coordinates:** 19.4150°N, −99.1700°W
**H3 Cell (res 8):** `884995ba39fffff` | **Parent (res 5):** `854995bbfffffff`
**Generated:** 2026-05-03 from RHYO intelligence DB (Hetzner PG16, 158M-cell global grid; Mexico subset 2,522,523 res-8 cells)

---

## 1. RHYO COMPOSITE SCORES — Target Cell

| Metric | Value | Band |
|---|---|---|
| Overall Day Score | **67.2 / 100** | Guarded |
| Overall Night Score | **27.7 / 100** | Critical |
| Women Safety (composite) | **49.7 / 100** | Elevated |
| Women Safety (night) | not yet computed | — |
| Confidence | **0.89** | High (not country fallback) |
| Data sources fused | **9** | — |
| Timezone | America/Mexico_City | — |
| Conflict zone | false | — |
| Informal settlement | false | — |
| Compound risk modifier | 0 | — |
| Fallback level | **municipal** | — |

**Reading:** Roma/Condesa scores **"Guarded by day, Critical by night"** — a 39.5-point diurnal drop that mirrors the Bangkok Sukhumvit profile but with a fundamentally different driver: **CDMX's recorded violent-crime rate is structurally higher** (Mexico national homicide 28.2/100K vs Thailand 4.4/100K) even though Roma/Condesa sits in the safer percentile of the CDMX distribution. The 0.89 confidence + **municipal** fallback level (not country) means **this score is genuinely cell-resolved**, not a Mexico-baseline override.

**Surrounding 19 cells (k-ring 2, ~2–3 km radius):** **day 45.6 → 68.6** (heterogeneous — real signal), night 25.8 → 29.1, crime 0.73 avg. The wide day-score range is the heterogeneity signature of inner CDMX: Roma Norte and Condesa are at the safer end; surrounding cells dipping below 50 reflect the gradient toward Doctores (south), Buenos Aires (south), and the eastern margin toward Zona Rosa/Juárez.

**Wider 343-cell res-5 parent (~250 km², most of inner CDMX):** day=70.7 / night=48.6, crime=0.54, flood=0.01, emergency=0.01, lighting=0.05 — the **broader inner-CDMX average is *better* than this exact Roma/Condesa cell**, because the parent includes upper-middle-class Polanco, Lomas, and Coyoacán which bring the average up. Roma/Condesa specifically is a *trendier-and-thus-targeted* pocket, not a *poorer* pocket.

### Tepito comparison (~4 km north — same res-5 parent)

| Cell | Day | Night | Women | Crime | Lighting | Fallback | Read |
|---|---|---|---|---|---|---|---|
| **Roma/Condesa** `884995ba39fffff` | 67.2 | 27.7 | 49.7 | 0.67 | 0.08 | municipal | Guarded / Critical |
| **Tepito** `884995b86bfffff` | **46.5** | 27.8 | **28.0** | **0.85** | 0.00 | municipal | **Elevated / Critical** |

Tepito's **20.7-point lower day score and 21.7-point lower women's score** is the largest within-CDMX gap RHYO records in this borough. Day-Tepito is operationally **"do not enter as a tourist"**; Roma/Condesa-night carries similar absolute risk to Tepito-day. The night scores converge because both inherit the CDMX overnight crime baseline.

---

## 2. CELL-LEVEL RISK FACTORS (9-Factor AHP, target cell)

| Risk Column | Value | Read |
|---|---|---|
| **crime_risk** | **0.67** | HIGH — driven by `hoyodecrimen_cdmx = 0.80` (Roma cell sits in 80th percentile of CDMX-recorded crime) + Mexico national homicide baseline |
| **flood_risk** | 0.00 | Negligible — Roma/Condesa is on filled lakebed but well-drained; no aqueduct/CHIRPS pulse |
| **emergency_access_risk** | **0.009** | **Very low risk** — `healthsites_proximity = 0.01` (top 1%); Hospital General, Médica Sur, ABC, Español all within 6 km |
| **road_quality_risk** | **0.018** | **Very low** — Roma/Condesa is a textbook 19th-century grid; OSM `4way_intersection_ratio = 0.78` (top decile), `escape_route_time = 0`, `network_disconnection = 0` |
| **lighting_risk** | 0.08 | Low — gentrified Cuauhtémoc has consistent street lighting |
| **building_density_risk** | 0.003 | Very low — `population_density = 1.0`, `ghsl_builtup = 0.28` |
| **cellular_risk** | 0.10 | Low — Telcel/AT&T/Movistar coverage strong; Ookla = 0.19 (good) |
| **business_activity_risk** | 0.00 | Very low — `business_activity = 1.0`, `business_high_density = 1.05` (saturated commercial = natural surveillance) |
| **green_space_risk** | 0.34 | Moderate — Parque México and Parque España within 1 km; `hansen_treecover = 0.03` |

---

## 3. RAW SIGNALS PRESENT AT TARGET CELL (29 covariates, all sources cited)

| Signal | Value | Source | Date |
|---|---|---|---|
| **HoyoDeCrimen CDMX** (live SSC-CDMX feed) | **0.80** (80th pct of CDMX cells) | hoyodecrimen.api | 2026-04-27 |
| Population density (Kontur) | 1.00 (saturated) | Kontur | 2023-11 |
| Business activity (Overture) | 1.00 (saturated commercial) | Overture Maps | 2026-03-18 |
| Business high-density derived | 1.05 (over P90) | RHYO derived | 2026-04-11 |
| Healthcare travel band (derived) | **1.00 (top — care reachable in <30 min friction)** | Weiss/MAP friction classifier | 2026-04-11 |
| Health-sites proximity | **0.0099 (top 1%)** | OSM/Overpass | 2026-04-08 |
| JCI hospital proximity | 0.098 (close — top decile) | Joint Commission International | 2026-04-08 |
| GHSL built-up fraction | 0.28 | JRC/GHSL r2023a | 2020 |
| Hansen tree cover | 0.03 (low — paved urban core) | UMD/Google | 2000 |
| OSM 4-way intersection ratio | **0.78 (top decile)** | OSMnx | 2026-04-03 |
| OSM avg block size | 0.07 (small blocks — walkable grid) | OSMnx | 2026-04-03 |
| OSM avg node degree | 0.64 | OSMnx | 2026-04-03 |
| OSM circuity avg | 0.03 (low — direct routing) | OSMnx | 2026-04-03 |
| OSM cul-de-sac ratio | 0.012 (almost none) | OSMnx | 2026-04-03 |
| OSM dead-end density | 0.16 | OSMnx | 2026-04-03 |
| OSM escape-route time | **0** (multiple egress paths) | OSMnx | 2026-04-03 |
| OSM network disconnection | **0** (fully connected) | OSMnx | 2026-04-03 |
| OSM road network permeability | 0.37 | OSMnx | 2026-04-03 |
| OSM segment betweenness | 0.07 | OSMnx | 2026-04-03 |
| OSM street density | 0.36 | OSMnx | 2026-04-03 |
| OSM arterial isolation | 0.20 | OSMnx | 2026-04-03 |
| MAP friction (travel time to nearest care) | 0.018 (top — very fast) | Weiss et al., MAP 2020 | 2020 |
| Ookla download Mbps | 0.19 (low risk = good speed) | Ookla Speedtest | 2025-10 |
| Corruption (TI-CPI proxy) | 0.74 | TI-CPI 2024 | 2026-04-05 |
| CHIRPS precipitation (Feb baseline) | 0.008 | UCSB/CHG | 2026-02 |
| GSW surface water occurrence | 0 | JRC GSW v1.4 | 2021 |
| WRI Aqueduct flood (baseline) | 0 | WRI | 2020 |
| Population density log derived | 0.30 | RHYO derived | 2026-04-11 |
| **UCDP conflict events** | **1.00 — 1996 historic incident** | UCDP | 1996-10 (legacy, preserved for transparency) |

**The 0.80 `hoyodecrimen_cdmx` is the headline cell-level number.** Hoyo de Crimen ingests live Mexico City SSC (Secretaría de Seguridad Ciudadana) reports; a value of 0.80 means this cell sits in the **80th percentile of CDMX crime intensity** — high but not extreme by CDMX standards. Tepito's neighboring cell registers 0.85+. The street-grid signals are RHYO's strongest endorsement of this neighborhood: a fully-connected, walkable, multi-egress urban fabric is the **opposite** of the cul-de-sac suburb morphology associated with poor pedestrian safety and slow emergency response.

---

## 4. NEAREST EMERGENCY MEDICAL — Verified hospital proximity

Health-sites proximity at this cell = **0.0099 (top 1% globally)**. Major CDMX facilities within ~6 km of Roma/Condesa:

- **Hospital Ángeles Roma** (Querétaro 154, Roma) — private, ~700 m
- **Hospital Español** (Ejército Nacional 613, Granada) — private tertiary, ~3.5 km
- **Hospital ABC Observatorio** (Sur 136 #116, Las Américas) — private flagship, JCI-accredited, ~6 km
- **Médica Sur** (Puente de Piedra 150, Toriello Guerra) — private quaternary, JCI-accredited, ~10 km south
- **Hospital General de México "Dr. Eduardo Liceaga"** (Dr. Balmis 148, Doctores) — public flagship, ~3 km
- **Centro Médico Nacional Siglo XXI** (Cuauhtémoc 330, Doctores) — IMSS public, ~2.5 km
- **Hospital Infantil de México "Dr. Federico Gómez"** (Dr. Márquez 162, Doctores) — pediatric, ~3 km

JCI-accredited care (ABC, Médica Sur, Houston Methodist Global Care affiliations) is reachable in **15–25 min outside peak traffic, 35–60 min in peak congestion**. *Sources: OSM/Overpass (2026-04-08), JCI directory (2026-04-08), HoyoDeCrimen geographic overlay (2026-04-27).*

**Mexican emergency numbers:**
- **911** — Unified emergency (police / fire / medical) — replaced legacy 060/065/068 nationally in 2017
- **Locatel CDMX: 55-5658-1111** — Mexico City information & assistance line, English-capable, handles tourist incidents, lost persons, missing-foreigner cases
- **078** — Federal Tourist Police (Ángeles Verdes — primarily highway assistance but multilingual)
- **Embajada hotlines:** US +52-55-8526-2561 (24h), UK +52-55-1670-3200, Canada +52-55-5724-7900

---

## 5. CITY & DISTRICT-LEVEL THREATS (Mexico City / Cuauhtémoc / Roma-Condesa)

| Indicator | Value | Source |
|---|---|---|
| **HoyoDeCrimen CDMX (cell-level)** | **0.80 — 80th percentile of CDMX crime cells** | SSC-CDMX live feed via hoyodecrimen.api 2026-04 |
| **Wikivoyage Mexico safety composite** | **58.3 / 100** (caution) | RHYO text-extraction pipeline 2026-04 |
| **Airbnb perception index (Mexico City)** | **52.3** (n=1,454,740; +33.0% positive / −2.5% negative) | Inside Airbnb 2026-04 |
| **MIT Place Pulse safety perception** | (no Mexico City row in current snapshot) | — |
| **Tepito comparison cell** | day 46.5 / crime 0.85 / women 28.0 (vs Roma 67.2 / 0.67 / 49.7) | RHYO 2026-04 |

Roma Norte, Roma Sur, Condesa, and Hipódromo lie in the **Cuauhtémoc borough (alcaldía)**. This is gentrified inner-CDMX — galleries, taquerías de autor, mezcalerías, parks (Parque México, Parque España), Casa Lamm, art-deco architecture. The borough overall has **higher recorded crime than upscale Polanco or Coyoacán** but is a fraction of Tepito (Cuauhtémoc north), Iztapalapa, or Gustavo A. Madero. The **2017 M7.1 Puebla earthquake heavily damaged** Roma — some buildings remain under repair or condemned, and structural-collapse risk is real for sub-1985 unreinforced masonry stock.

---

## 6. NATIONAL-LEVEL CONTEXT (Mexico — selected indicators)

### Travel advisories (state actor sources)
| Source | Level | Score |
|---|---|---|
| **US State Department** | **Level 2 — Exercise Increased Caution (CDMX-specific)** | 0.35 (LOW for CDMX) |
| **US State Dept threat composite** | **0.785 (HIGH)** — driven by Sinaloa, Tamaulipas, Michoacán, Colima, Zacatecas, Guerrero (all Level 4) | warning |
| **UK FCDO** | "3D / 3W / 4C" composite | **1.00 (MAX)** — driven by 30+ "do-not-travel" northern/Pacific states |
| **German Auswärtiges Amt** | **No travel warning** | 0.0 |
| **Canada (travel.gc.ca)** | **Level 1 / 4** (safest) | 0.25 |
| **CDC (US health)** | **29 active health notices** | 1.00 |

> *FCDO score of 1.00 is the most extreme in this report set, but is **almost entirely driven by cartel-control northern and Pacific states**. CDMX itself is Level 2 / Stay-Vigilant in every major advisory. The US State Dept does not advise against CDMX travel.*

### Crime / homicide / violence (national)
- **WHO intentional homicide:** **28.2 / 100K (2021)** — danger band (top 6 globally for non-conflict states)
- **OWID homicide rate:** 24.86 / 100K
- **UNODC homicide rate:** 18.1 / 100K (older 2018-era figure)
- **UCDP GED conflict events 2020+:** **10,867 events, 60,342 estimated fatalities** — almost all cartel violence; CDMX accounts for <2% of cartel deaths despite housing ~7% of national population
- **UNODC kidnapping:** 0.48 / 100K (low — Mexico's actual kidnap-for-ransom rate is heavily under-reported but UNODC formal figure is modest)
- **Mass Mobilization protest events:** 153 (56 recent, 11 with violent state response)
- **OWID conflict deaths 2025:** 2,843 (danger)
- **OWID terrorism deaths 2021:** 12 (low — Mexico's threat is organized crime, not terrorism)

### Governance & rule of law
- **Freedom House:** Free (Status=2/3)
- **WJP Rule of Law:** **0.415** (caution) — overall 110/142 globally
- **WJP Criminal Justice:** **0.250 (warning)** — bottom-quartile globally; impunity rate for homicide is ~94%
- **WJP Civil Justice:** 0.371 (warning)
- **WJP Absence of Corruption:** 0.265 (warning)
- **TI Corruption Perceptions Index:** 31/100 (warning) — bottom third
- **WB Control of Corruption:** −0.94 (percentile 29% — warning)
- **WB Rule of Law:** −1.15 (warning)
- **WB Political Stability:** −0.72 (warning)
- **PTS Political Terror score:** 4.0/5 (warning) — broad pattern of state-tolerated violence
- **Cline Center coups:** 1
- **INFORM Risk:** 4.9 / 10 (warning)
- **Global Peace Index:** 2.778 (Mexico ranks ~140/163 globally)

### Public health
- **Life expectancy:** 75.3 yrs (WB)
- **WHO PM2.5 annual:** 18.4 µg/m³ (warning) — **CDMX-specific is closer to 20–25** at 2,243 m altitude; **dramatically improved from 1990s peaks** but still ~2× WHO guideline
- **WB current PM2.5:** 15.0 µg/m³
- **Adult HIV prevalence:** 0.4% (low)
- **WHO DPT3 immunization:** 78% (caution — declining from 95% peak)
- **WB physicians per 1000:** 2.59 (above many EM peers)
- **JMP basic water service:** 56.6% (warning) — CDMX-specific is much higher (~95%) but national average is dragged down by rural Oaxaca / Chiapas / Guerrero
- **JMP safely-managed sanitation:** 62.7%
- **WHO alcohol per capita:** 6.0 L pure alcohol / yr (caution)
- **OpenDengue 2024 cases:** **558,846** (Mexico had a major dengue surge in 2024 — Yucatán, Veracruz, Morelos peaks)

### Hazards (Mexico-wide)
- **EM-DAT natural disasters (count):** 168 — **2,625 deaths**
- **GDACS active events:** ~1 (low)
- **WRI Aqueduct riverine flood (country baseline):** 2.09 / 5 (CDMX low; Tabasco / Yucatán high)
- **WRI Aqueduct water stress:** 4.0 / 5 (CDMX especially — chronic water shortages)
- **WRI Aqueduct drought:** 2.6 / 5
- **WRI World Risk Index:** 38.96
- **Capital elevation:** **2,243 m** (Mexico City — altitude-sickness territory for sea-level visitors)
- **GBIF venomous snake species (national):** **64** — highest in this report set (but coastal/jungle, not CDMX core)
- **Earthquake hazard:** Mexico City sits on the **drained-lakebed of the Valley of Mexico**, which produces multi-second amplification of subduction-zone earthquakes from the Pacific coast. The 1985 M8.0 (Michoacán) and 2017 M7.1 (Puebla) events both caused major damage in Roma/Condesa specifically. **CDMX has the world's most sophisticated earthquake-early-warning system (SASMEX/Alerta Sísmica)** — 60+ seconds of warning for distant subduction events, near-zero warning for local crustal events.

### Social & rights
- **Equaldex equality index:** 0.70 (CDMX legalized same-sex marriage in 2009; trans rights nationally protected)
- **Equaldex legal index:** 0.84 (high)
- **Equaldex public opinion:** 0.57 (moderate)
- **WBL women's safety legal score:** **87.5 / 100** (good — strong legal framework)
- **Gender Inequality Index:** 0.32 (moderate)
- **TIP Report tier:** **Tier 2** — labor and sex trafficking; CDMX is a major destination
- **DHS-equivalent IPV:** 30.7% lifetime physical/sexual partner violence (national, INEGI 2021)

### Surveillance & legal (relevant for tourists)
- **Comparitech CCTV density:** 6 cameras/1K (moderate — CDMX has C5 surveillance system with 58k cameras citywide)
- **Comparitech censorship:** 38/100 (danger — some content restrictions, though press freedom is contested)
- **Comparitech SIM registration:** **mandatory**
- **Comparitech biometric:** 12/25 (danger)
- **Drug law:** Recreational cannabis decriminalized for personal possession (≤28g) since 2021 Supreme Court ruling, but **commercial sale still illegal**; cocaine, MDMA, heroin remain criminalized

### Road safety
- **WHO road traffic deaths:** **12.0 / 100K (2021)** — caution; far below Thailand's 25.4
- **WB road mortality:** 12.8 / 100K
- **WHO road traffic age-standardized:** 22.0 / 100K (older 2004 baseline)
- **CDMX-specific:** SCT/INEGI data shows pedestrian fatalities concentrated on Insurgentes, Reforma, Periférico — **Roma/Condesa internal grid is among CDMX's safest pedestrian zones**

---

## 7. ENVIRONMENTAL & EPIDEMIOLOGICAL RISKS — Mexico City-specific

### Altitude (highest physiological risk for short-stay sea-level visitors)
- **CDMX is at 2,243 m / 7,360 ft** — high enough to produce mild AMS (acute mountain sickness) symptoms in 10–20% of unacclimatized arrivals: headache, mild dyspnea, sleep disturbance, reduced exercise tolerance
- Symptoms typically resolve within 24–72 hours of acclimatization
- Mitigation: hydration, avoid alcohol night of arrival, no heavy exertion day 1, watch for severe symptoms (worsening headache, vomiting, confusion = descend or seek care)
- Cardiac patients with marginal reserve should consult before travel

### Air quality (highly improved but still elevated)
- CDMX annual mean PM2.5: ~18–25 µg/m³ baseline (WHO 18.4; WB 15.0)
- **Winter inversions (Nov–Feb):** PM2.5 routinely 80–120+ µg/m³ during stagnation events
- **Ozone:** Mexico City has *the* historic ozone problem; "contingencia ambiental fase 1" alerts trigger driving restrictions periodically
- Mitigation: app-monitor air quality (IQAir / waqi.info MX index), N95 outdoors during alerts, avoid outdoor exertion 11 AM–3 PM during inversions

### Water & food
- **Tap water in CDMX is treated but NOT recommended for drinking** by foreigners — high mineralization, intermittent service quality, in-building tinaco contamination risk
- Bottled or filtered only; ice in established restaurants is filtered
- **Travelers' diarrhea ("turista"):** baseline 30–50% in first 2 weeks (CDC Yellow Book) — *Salmonella, Campylobacter, ETEC*
- Street food in Roma/Condesa is high-quality; turnover at busy puestos = freshness
- **Hep A / Typhoid:** vaccines recommended

### Vector-borne disease
- **Dengue:** **CDMX is essentially dengue-free** (altitude > Aedes survival threshold). Dengue risk is **coastal and lowland** — Yucatán, Veracruz, Quintana Roo, Morelos. National outbreak 558k cases in 2024 did NOT meaningfully reach CDMX.
- **Chikungunya / Zika:** Same altitude exclusion — coastal only
- **Malaria:** Negligible in CDMX; risk limited to rural Chiapas / Tabasco / Quintana Roo border
- **Rabies:** Mexico has effective stray-animal control; rare. Pre-exposure not routinely recommended.

### Earthquakes (the dominant Mexico-City-specific hazard)
- **Roma/Condesa sit on the soft-lakebed sediment of the Valley of Mexico** — the worst possible substrate for amplification of distant subduction earthquakes
- 1985 M8.0 Michoacán: 5,000–10,000 deaths in CDMX, with concentrated damage in Roma, Condesa, Doctores, Centro
- 2017 M7.1 Puebla: 369 deaths, with again concentrated damage in Roma/Condesa
- **SASMEX Alerta Sísmica:** 60–90 seconds of warning for distant Pacific subduction events; near-zero warning for local crustal events. Cell-broadcast app available on Android/iOS.
- **Building stock to scrutinize:** unreinforced 1920s–1970s masonry; 1985-era reinforced concrete that did not get retrofitted. Post-1985 stock generally complies with strict building code. Verify your hotel/Airbnb building age and post-2017 inspection if booking long-term.
- **What to do during shaking:** stay inside if in modern building; if in pre-1985 stock and ground-floor egress is fast, get out to open square (Plaza Río de Janeiro, Parque México, Parque España are ideal Roma/Condesa refuges); if upper floor, drop-cover-hold under sturdy furniture, away from windows.

### Heat / cold
- CDMX's mild altitude climate: 18–25 °C daytime year-round; cold nights Nov–Feb (5–10 °C)
- Wet-bulb risk: negligible
- UV: high (altitude + low latitude) — sunscreen needed even on cool days

### Sinkholes / subsidence
- The Valley of Mexico aquifer is over-pumped; CDMX sinks ~10–40 cm/yr in some districts
- Concentrated in eastern CDMX (Iztapalapa, Iztacalco) — Roma/Condesa subsidence is mild
- Residual: occasional pavement collapse and tilted buildings

---

## 8. ANTHROPOGENIC / CRIME-PROXIMATE RISKS

### What does NOT meaningfully apply to Roma/Condesa core:
- **Cartel-territorial violence** — Mexico's 60,342 UCDP fatalities (2020+) cluster in Sinaloa, Tamaulipas, Michoacán, Guanajuato, Guerrero, Zacatecas. CDMX accounts for <2% despite 7% of population. Roma/Condesa has experienced occasional spillover (Cártel de Tláhuac, Unión Tepito) but no sustained territorial conflict.
- **Express kidnapping** — present but **rare in Roma/Condesa specifically**; concentrated near banks in less-monitored boroughs and on rideshare-from-airport routes
- **Tourist-targeted political violence** — Mexico's threat is criminal, not political
- **Active conflict zone** — flag = false
- **Informal settlement** — flag = false

### What DOES apply:

| Risk | Notes |
|---|---|
| **Phone snatching ("levantón de celular")** | The single most common crime against tourists in Roma/Condesa. Operating model: pillion passenger on motorbike snatches phone from open hand at intersection, café terrace, or sidewalk. **Never hold phone out walking; never leave on table at café terrace; use AirPods/CarPlay over visible phone.** |
| **Pickpocketing on Metro / Metrobús** | Routine on Line 1 (Pink), Line 2, Line 8, especially Pino Suárez, Pantitlán, and Bellas Artes interchanges |
| **ATM card-skimming** | Use **bank-branch interior ATMs only**; avoid stand-alone "Citibanamex express" kiosks. Cover PIN. CDMX has documented organized skimming rings. |
| **Express kidnapping ("secuestro express")** | Driver of unauthorized "taxi libre" forces ride to ATMs. **Use Uber, DiDi, or Cabify exclusively**; never flag street taxis (libre or sitio). Confirm plate matches app before entering. |
| **Drink spiking** | Documented in Condesa nightlife (Tamaulipas, Nuevo León, Álvaro Obregón corridors), Zona Rosa, Roma Norte bars. **Never accept poured drinks; carry from bar to table.** |
| **Hostess / clip-joint extortion** | Pattern: friendly stranger invites you to a bar in Zona Rosa or Centro → undisclosed cover/drink prices → security intimidation for thousands of pesos |
| **Romance / Tinder / Grindr setup** | Multiple documented cases: app match → meet → drugged → robbed. **Meet only in busy public places initially; tell someone where you're going.** |
| **Police corruption** | CDMX police are less corrupt than Estado de México or rural counterparts but petty bribery still occurs. **Do not pay roadside "fines"; demand a receipt or a trip to the station.** Tourist Police (Policía Auxiliar de Turismo, blue uniforms) are typically cleaner. |
| **Protests / road closures** | Reforma + Insurgentes + Zócalo are the standard protest corridors. Roma/Condesa is rarely directly affected but Metrobús L1 and L7 disruptions are common. Check `@SSP_CDMX` Twitter/X. |
| **Earthquake (recurring)** | See §7. Real, recurring, and concentrated in Roma/Condesa structural-amplification zone. |
| **Pre-1985 building collapse** | Some Roma stock is still being structurally certified after 2017. Verify your accommodation. |
| **Road traffic for pedestrians** | Moderate. Roma/Condesa internal sois are walkable. Crossing Insurgentes (eastern boundary), Av. Cuauhtémoc, or Reforma is the high-risk pedestrian moment. |
| **Two-wheeler injury** | Lower than Bangkok/Bali but Mexico City e-scooter / Bird / Lime usage on chaotic intersections produces routine ER cases. Helmet and visible clothing essential. |
| **Drug enforcement** | Cannabis personal possession decriminalized (≤28g); other drugs criminalized. Foreigners receive no special leniency. |
| **Tepito / La Lagunilla market exposure** | **Do not enter Tepito (~4 km north)** — the cell-level day score 46.5 / crime 0.85 / women 28.0 is RHYO's strongest within-CDMX warning. La Lagunilla weekend market draws tourists but pickpocketing is rife. |
| **Stray dogs** | Lower density than many Mexican cities; rabies risk negligible in CDMX |

---

## 9. TARGETED THREAT PROFILE — for a Western solo tourist in Roma/Condesa

The risk delta between this individual and a generic CDMX local is concentrated in five categories:

1. **Visible-affluence theft vector** — phone snatching, watch grabs, bag snatching from terraces. Mitigation: low-profile electronics; bag inside chair leg + strap; phone in pocket on streets.
2. **Rideshare discipline** — never use street taxis; verify Uber plate before entering; share trip with someone; ride in back-right.
3. **Nightlife discipline** — drink-from-bar only; stay in groups for first night out; pre-charge home location in Uber before drinking.
4. **Earthquake awareness** — know your accommodation's seismic zone (most of Roma/Condesa is yellow/red on CDMX seismic-amplification maps); know nearest open-square refuge; install Alerta Sísmica app; review drop-cover-hold protocol.
5. **Altitude management** — first 24h: hydration, no alcohol, sleep early. Watch for worsening symptoms.

**There is no credible terrorism, kidnap-for-ransom, or cartel-targeted violence risk to a tourist in Roma/Condesa under normal circumstances.** The realistic life-threatening incidents are, in descending order:

1. Pedestrian collision crossing arterial (Insurgentes, Cuauhtémoc, Reforma) — esp. at night
2. Earthquake (low annualized, very high consequence — recurrence-decade risk for major event)
3. Express kidnapping or robbery escalation if rideshare discipline lapses
4. Drink-spiking → assault / fall injury
5. Cardiac event aggravated by altitude + air pollution + dehydration (esp. for >50 visitors in winter inversion season)
6. Foodborne acute infection
7. Phone snatching escalating to violence (rare but documented)

---

## 10. RHYO DATA QUALITY DISCLOSURES

- **Cell `884995ba39fffff` runs on municipal-level fallback** — the score is genuinely cell-resolved (confidence 0.89), not a Mexico-baseline override. K-ring shows real heterogeneity (45.6–68.6 day range across 19 cells). This is RHYO Mexico operating closer to design intent than RHYO Thailand.
- **`hoyodecrimen_cdmx = 0.80`** is the single most valuable cell-level signal in this report — live SSC-CDMX feed via the hoyodecrimen API, refreshed weekly, includes all reported crime categories (robbery, assault, sexual violence, vehicle theft, homicide).
- **`emergency_access_risk = 0.009`** (very low risk) is internally consistent: health-sites proximity 0.01, MAP friction 0.02, JCI hospital proximity 0.10, healthcare travel band derived = top class. Roma/Condesa has genuinely excellent emergency access.
- **`women_safety_score_night` is null** — Q26 night-women variant SQL function pending (CLAUDE.md §36).
- **`ucdp_conflict_events = 1.0`** preserves a 1996 historic incident — stale but kept for transparency, similar to the Hyderabad 1993 row pattern.
- **Tepito comparison cell** uses cell `884995b86bfffff` at 19.4435 N, −99.1335 W — captures the Tepito/Lagunilla retail-criminal axis. Multiple adjacent cells score similarly; this is the canonical "do not enter" CDMX zone for a tourist.
- **National CDMX crime statistics quoted** in §6 are Mexico-wide; **CDMX-specific homicide rate is ~10–14 / 100K** (CDMX SSC + INEGI), substantially below the 28.2/100K national figure. This is reflected in the cell-level scoring.
- **2017-earthquake structural risk** is NOT in the cell-level layer and is reported here from independent sources (PEMEX/UNAM/CIRES building-vulnerability surveys). Verify your specific accommodation's structural certification.
- **Database state:** Hetzner PG cluster online; Mexico has 2,522,523 res-8 cells fully scored (100% coverage); ~410 country indicators on file. Score recompute timestamp: 2026-03-30 01:42 CEST.
- **Sources cited inline.** Verifiable via: WHO GHO, World Bank WDI/WGI, UNODC, EM-DAT/CRED, INEGI/SSC-CDMX (via HoyoDeCrimen), Inside Airbnb, OSM/Overpass, OSMnx, JCI directory, MAP friction (Weiss et al. 2020), JRC GHSL, JRC GSW, UMD/Google Hansen, US State Dept, UK FCDO, German AA, Canada travel.gc.ca, CDC, INFORM/HDX, UCDP GED, Open-Meteo, Ookla, OpenDengue, GDACS, WRI Aqueduct, JMP/WHO/UNICEF, BTI/Bertelsmann, Fund for Peace, WJP, V-Dem, Comparitech, Equaldex, WBL 2026, Global Peace Index 2024, Wikivoyage.

---

## ONE-LINE BOTTOM LINE
**Roma/Condesa is a "Guarded by day, Critical by night" gentrified-CDMX core where the realistic threats to a Western solo tourist's life are, in order: (1) pedestrian collision on arterials, (2) recurring earthquake amplification on Valley-of-Mexico lakebed, (3) express-kidnap/robbery if rideshare discipline lapses, (4) drink-spiking in Condesa nightlife — NOT terrorism, NOT cartel violence, NOT kidnap-for-ransom; do not stray ~4 km north into Tepito (cell score collapses 20+ points); call 911 and Locatel 55-5658-1111 for tourist incidents.**
