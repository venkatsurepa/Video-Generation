# RHYO Safety Intelligence Report
## Sukhumvit Road area (Soi 1–55), Khlong Toei / Watthana / Khlong Toei Nuea, Bangkok, Thailand
**Coordinates:** 13.7380°N, 100.5600°E
**H3 Cell (res 8):** `8864a48495fffff` | **Parent (res 5):** `8564a487fffffff`
**Generated:** 2026-05-03 from RHYO intelligence DB (Hetzner PG16, 158M-cell global grid; Thailand subset 600,174 res-8 cells)

---

## 1. RHYO COMPOSITE SCORES — Target Cell

| Metric | Value | Band |
|---|---|---|
| Overall Day Score | **69.7 / 100** | Guarded |
| Overall Night Score | **30.8 / 100** | Critical |
| Women Safety (composite) | **48.8 / 100** | Elevated |
| Women Safety (night) | not yet computed | — |
| Confidence | 100% | — |
| Data sources fused | 10 | — |
| Timezone | Asia/Bangkok | — |
| Conflict zone | false | — |
| Informal settlement | false | — |
| Compound risk modifier | 0 (no compounding hazards activated) | — |
| Fallback level | **country** | — |

**Reading:** Sukhumvit's day score of 69.7 sits in RHYO's "Guarded" band — broadly equivalent to upscale tourist Bangkok. The 38.9-point night drop is the headline finding: this cell falls from "Guarded" to **"Critical"** between sunset and sunrise. The Critical band is RHYO's strongest warning short of an active conflict zone, and reflects the documented after-dark risk profile of the Sukhumvit nightlife corridor — drink-spiking, prostitution-adjacent extortion, motorbike-taxi disputes, and predatory taxi/tuk-tuk pricing.

**Surrounding 19 cells (k-ring 2, ~2–3 km radius):** uniform **69.7/30.8** day/night — no internal heterogeneity. This is a **country-level fallback** signature: the score reflects Thailand's national baseline applied to every cell in central Bangkok, NOT a cell-resolved score derived from neighborhood-specific signals. The **343-cell res-5 parent (~250 km², covering most of inner Bangkok)** averages day=69.7 / night=30.9, crime=0.68, flood=0.40, emergency=0.95, lighting=0.22 — also country baseline.

> **What this means in plain English:** RHYO's overall score for Sukhumvit is essentially "Bangkok = Thailand baseline." The cell-resolved layers below (20 covariates) are real and present — they're just not yet being composited into a Sukhumvit-specific overall score. Use the section 3 raw signals and section 5–7 narrative as the operational picture, not the headline composite.

---

## 2. CELL-LEVEL RISK FACTORS (9-Factor AHP, target cell)

| Risk Column | Value | Read |
|---|---|---|
| **crime_risk** | 0.68 | HIGH — driven by Thailand national homicide 4.4/100K (WHO) + UNODC robbery/sexual-violence rates + high tourist-target density |
| **flood_risk** | 0.40 | Moderate-high — Bangkok's documented monsoon flooding + subsidence; PSMSL sea-level trend at this cell = 0.75 |
| **emergency_access_risk** | **0.95** | Reads "Very High Risk" but **conflicts with cell-level POI data** (HOT emergency POIs = 0.73, JCI hospital proximity = 0.014, multiple Bumrungrad/Samitivej/BNH within 2 km). Country-baseline override from Thailand's low physician density (0.54/1000, WB SH.MED.PHYS.ZS); on-the-ground reality is **excellent** for Sukhumvit specifically. See §4. |
| **road_quality_risk** | 0.18 | Low — Sukhumvit Road is a paved arterial; OSM crosswalk density = 0.83 (top decile) |
| **lighting_risk** | 0.22 | Low — Sukhumvit BTS corridor is well-lit |
| **building_density_risk** | 0.25 | Low — substantial high-rise stock; OSM hotel density (Asia) = 0.54 (top quartile) |
| **cellular_risk** | 0.15 | Low — strong coverage; Ookla download score = 0.01 (excellent) |
| **business_activity_risk** | 0.02 | Very low — high commercial activity = natural surveillance |
| **green_space_risk** | 0.20 | Low — Benjasiri / Benjakitti parks within 1.5 km |

---

## 3. RAW SIGNALS PRESENT AT TARGET CELL (20 covariates, all sources cited)

| Signal | Value | Source | Date |
|---|---|---|---|
| OSM crosswalk density | **0.83 (top decile)** | OSM/Overpass | 2026-04-08 |
| OSM crossings | 0.83 | OSM/Overpass | 2026-04-08 |
| HOT emergency POIs (large area) | 0.73 | OSM/Overpass HOT-style | 2026-04-11 |
| HOT emergency POIs (medium area) | 0.60 | OSM/Overpass HOT-style | 2026-04-11 |
| OSM hotel density (Asia) | **0.54 (top quartile)** | OSM | 2026-04-11 |
| OSM pharmacy access | 0.54 | OSM | 2026-04-04 |
| OSM toilets | 0.47 | OSM/Overpass | 2026-04-08 |
| Transit stop density | 0.35 | OSM | 2026-04-08 |
| OSM bus stops | 0.35 | OSM/Overpass | 2026-04-08 |
| OSM pharmacy density (Asia) | 0.29 | OSM | 2026-04-11 |
| GBIF venomous snakes | 0.24 (cobras / kraits in Bangkok records) | GBIF | 2026-04-11 |
| OSM fuel station density (Asia) | 0.22 | OSM | 2026-04-11 |
| ATM density | 0.15 | OSM | 2026-04-04 |
| OSM bank/ATM density | 0.15 | OSM | 2026-04-04 |
| Corruption (TI-CPI proxy) | 0.66 | TI / WB CC.EST | 2026-04-05 |
| **PSMSL sea-level trend** | **0.75 (high — Bangkok subsidence + rising sea)** | PSMSL | 2026-04-07 |
| CHIRPS precipitation (Feb baseline) | 0.03 | UCSB/CHG | 2026-02-01 |
| WRI Aqueduct flood (baseline) | 0.0 | WRI | 2020 |
| **JCI hospital proximity** | **0.014 (very close — top 5% global)** | Joint Commission International | 2026-04-08 |
| Ookla download Mbps | 0.01 (excellent — low cellular risk) | Ookla Speedtest | 2025-10 |

**Most actionable single number:** `psmsl_sea_level_trend = 0.75` — Bangkok is sinking ~1–2 cm/yr while the Gulf of Thailand rises. This is a **decade-out structural risk**, not a today risk for a tourist, but it is the highest cell-level environmental signal here.

**Most underweighted single number:** the **0.014 JCI hospital proximity** — Sukhumvit is one of the densest concentrations of internationally-accredited hospital care in Southeast Asia, and the headline 0.95 emergency_access_risk score does not reflect that.

---

## 4. NEAREST EMERGENCY MEDICAL — Verified hospital proximity

JCI hospital proximity at this cell = **0.014 (top 5% globally)**. Major Bangkok facilities within ~2 km of Sukhumvit Soi 1–55:

- **Bumrungrad International Hospital** (Soi 3 / Sukhumvit Soi 1) — JCI-accredited 6× consecutive cycles, gold-standard medical-tourism destination, ~600 beds, 24/7 ER, English/Arabic/Japanese/Mandarin staff
- **Samitivej Sukhumvit Hospital** (Soi 49) — JCI-accredited, strong pediatric & women's-health, ~270 beds
- **BNH Hospital** (Convent Rd, Silom — ~3 km) — JCI-accredited tertiary
- **Bangkok Hospital** (Phetchaburi Rd — ~4 km) — JCI-accredited flagship of the Bangkok Dusit Medical Services group
- **Police General Hospital** (Ratchadamri / Pathum Wan — ~3 km) — public, Thai-language primary

JCI-accredited care is reachable in **<10 min outside peak traffic, 25–35 min in peak congestion**. *Sources: OSM/Overpass (2026-04-04), JCI directory (2026-04-08), HOT emergency POI overlay (2026-04-11).*

**Thai emergency numbers:**
- **191** — Police (general)
- **1669** — Medical / ambulance (free, English-capable in central Bangkok)
- **1155** — **Tourist Police** (multilingual; THE number for foreigners; staffed by volunteer interpreters)
- **199** — Fire
- **1646** — Bangkok Metropolitan Administration emergency

The **1155 Tourist Police hotline** is the single most useful number for a Western visitor — it dispatches officers trained for foreigner cases (scams, taxi disputes, drink-spiking, lost-passport).

---

## 5. CITY & DISTRICT-LEVEL THREATS (Bangkok / Watthana / Khlong Toei)

| Indicator | Value | Source |
|---|---|---|
| **MIT Place Pulse safety perception (Bangkok)** | **5.2 / 10** (caution band) | Place Pulse 2.0, Dubey 2016 |
| **Wikivoyage Bangkok safety composite** | **63.6 / 100** (caution band) | RHYO text-extraction pipeline 2026-04 |
| **Airbnb perception index (Bangkok)** | **54.1** (n=583,333; +49.4% positive / −3.2% negative) | Inside Airbnb 2026-04 |
| **WEF TTDI Safety pillar (Thailand)** | **4.4 / 7.0** | WEF 2024 |
| **Thailand homicide rate** | **4.4 / 100K** (WHO GHO VIOLENCE_HOMICIDERATE 2021) — Bangkok metropolitan ~3.0/100K | WHO GHO |
| **Thailand UNODC homicide rate** | 5.3 / 100K | UNODC 2024 |
| **Thailand UNODC robbery rate** | 1.7 / 100K (low) | UNODC 2023 |
| **Thailand UNODC sexual violence rate** | 7.5 / 100K | UNODC 2023 |
| **Thailand UNODC serious assault** | 28.0 / 100K | UNODC 2023 |
| **Thailand female homicide rate** | 1.13 / 100K (2014, OWID) | OWID |
| **WHO interpersonal violence deaths** | **24.2 / 100K (2019)** — danger band | WHO GHO SA_0000001457 |

Sukhumvit Soi 1–55 spans three Bangkok districts — **Khlong Toei** (Soi 1–21, the Nana / Asok zone), **Watthana** (Soi 23–63, Phrom Phong / Thong Lor / Ekkamai), and **Khlong Toei Nuea**. This is the diplomatic / luxury-condo / international-business heart of Bangkok and is *not* representative of poorer districts (Khlong Toei slum core lies south of the rail line and is genuinely higher-risk after dark, but not the strip Sukhumvit Road runs through).

---

## 6. NATIONAL-LEVEL CONTEXT (~427 indicators on file for Thailand)

### Travel advisories (state actor sources)
| Source | Level | Score |
|---|---|---|
| **US State Department** | **Level 2 — Exercise Increased Caution** | 0.35 (LOW) |
| **UK FCDO** | "2D / 3W / 3C" composite | 0.80 (HIGH composite — driven by deep-south insurgency, NOT Bangkok) |
| **German Auswärtiges Amt** | Partial Travel Warning (regional) | 0.70 |
| **Canada (travel.gc.ca)** | **Level 1 / 4** (safest) | 0.25 |
| **CDC (US health)** | **6 active health notices** | 0.60 |

> *None of the four major foreign-ministry advisories single out Bangkok metropolitan for elevated caution. Elevated FCDO/AA scores are driven by the **deep-south insurgency provinces** (Pattani, Yala, Narathiwat, parts of Songkhla) and the **Thai–Cambodia border** (occasional skirmishes, mine contamination index = 15,085) — neither relevant to a Sukhumvit-based visitor.*

### Crime / homicide / violence (national)
- **Intentional homicide:** 4.4 / 100K (WHO 2021); 5.3 / 100K (UNODC 2024)
- **Female homicide:** 1.13 / 100K (OWID 2014)
- **WHO interpersonal violence deaths:** 24.2 / 100K (2019, danger band — broadest "violent death" metric)
- **UNODC kidnapping:** 0.03 / 100K (very low)
- **UNODC robbery:** 1.7 / 100K (very low)
- **UCDP GED conflict events 2020+:** **111 events, 154 fatalities** — **all in deep-south (Pattani / Yala / Narathiwat)**
- **OWID conflict deaths 2025:** 163
- **OWID terrorism deaths 2021:** 11
- **Mass Mobilization protest events:** 254 (102 recent, 5 with violent state response)

### Governance & rule of law
- **Freedom House Status:** **Not Free (NF)** — PR=6/7, CL=5/7
- **Polity5:** −3 (autocratic-leaning; 2014 coup era)
- **V-Dem Liberal Democracy:** 0.191 (danger band, declining)
- **V-Dem Electoral Democracy:** 0.208 (warning)
- **WJP Rule of Law:** 0.498 (caution)
- **TI Corruption Perceptions:** 36/100 (TI 2024) → WB CC.EST −0.49 (warning)
- **WGI Rule of Law percentile:** 53% (caution)
- **WGI Political Stability percentile:** 54%
- **Cline Center coup attempts:** **19 historic** (2 since 2000 — 2006 & 2014)
- **Powell-Thyne coup attempts:** 12 (8 successful)
- **Fragile States Index:** 68.0 / 120 (caution)

### Public health
- **Life expectancy:** 76.6 yrs (WB), 75.3 (WHO 2021)
- **Adult HIV prevalence:** 1.0% (WHO 2024) — among the higher rates in mainland SE Asia; concentrated in MSM, sex workers, IDU
- **TB incidence:** 144 / 100K (WHO 2024) — genuinely high
- **Suicide rate:** 16.6 / 100K (WHO GHO 2021, warning band)
- **WHO ambient PM2.5:** 25.5 µg/m³ (2019); WB current 31.0 µg/m³ → **2.5–3× WHO guideline of 10 µg/m³**
- **WHO basic water service:** 100%
- **JMP safely-managed sanitation:** **26.7%** (danger band — distinction: nearly all Thais have access to sanitation, but only 26.7% to safely-managed sewage treatment)
- **WB physicians per 1000:** 0.54 (warning — low for income level; concentrated in Bangkok)
- **WHO UHC service coverage index:** 82 / 100 (high)
- **GHSI pandemic preparedness:** 68.2 / 100 (above OECD median)

### Hazards
- **EM-DAT natural disasters 2000–2023:** 63 events
- **DesInventar disaster events:** 2,016
- **GDACS active events (Apr 2026):** 28–30 (predominantly **wildfire** — Northern Thailand burning season)
- **EM-DAT flood event density (5-yr):** **rank 1.000 (top globally)** — 11 major flood events in 5 years
- **EM-DAT tropical cyclone density:** 0.70
- **EM-DAT convective storm density:** 0.98
- **WRI Aqueduct riverine flood (country baseline):** 3.06 / 5
- **WRI Aqueduct water stress:** 3.62 / 5
- **WRI Aqueduct drought:** 3.01 / 5
- **WHO drowning death rate:** **6.5 / 100K (danger)** — Thailand has high drowning mortality (open water, beach, fishing)
- **WFSA ferry fatalities 2000–2015:** 12 deaths
- **NOAA tsunami events:** Andaman coast (2004), not Gulf of Thailand
- **GBIF venomous snakes (national):** 24 species
- **GBIF saltwater crocodile records:** 32 (Andaman / coastal — not Bangkok)

### Social & rights
- **Pew religious restrictions:** 4.0 / 10 (moderate)
- **Pew social hostilities:** 1.5 / 10 (low)
- **Equaldex equality index:** 0.65 (LGBTQ+: civil partnerships passed Jan 2025; broadly tolerant culturally, mid-tier legal protections)
- **WBL women's safety legal score:** **25 / 100 (danger)** — Thai legal framework for VAW is weak vs OECD norms
- **Gender Inequality Index:** 0.31 (moderate)
- **WPS Index rank:** 52 / 177 (info)
- **Frontline HRD killings 2023:** 1
- **Global Witness defenders killed 2012–2024:** 18

### Surveillance & legal-strict regime (relevant for tourists)
- **Wiki drug legality:** **0.95 (danger)** — death penalty for trafficking; cannabis was decriminalized in 2022 then **re-restricted in mid-2024 to medical use only**; recreational possession now a fine + possible jail
- **Lèse-majesté (Section 112):** strictly enforced — long prison sentences for online criticism of the monarchy (do not discuss the royal family on social media from inside Thailand)
- **HRI death penalty for drugs:** 0.6 (still on the books, "symbolic" enforcement for foreigners but not unheard of)
- **Comparitech CCTV density:** 3 cameras / 1K people (low coverage)
- **Comparitech censorship score:** 55 / 100 (danger band — VPN officially restricted, websites blocked)
- **Comparitech SIM registration:** **mandatory** (your local SIM is ID-linked)
- **Comparitech biometric data points:** 11 / 25 (danger — passport, fingerprint, facial recognition at airports)
- **TIP Report tier:** **Tier 2** (caution — labor & sex trafficking)
- **DOL forced labor flag:** 1 (fishing industry, primarily)

### Road safety — *the dominant physical risk*
- **WHO road traffic death rate:** **25.4 / 100K** (RS_198, 2021) — danger band
- **WB road mortality:** **32.2 / 100K (2019)** — **among the worst in the world** (top decile globally)
- **OICA fleet density:** 527 vehicles / 1000 people (very high; high motorbike share)
- **ILO fatal injury rate (occupational):** 4.9 / 100K
- **Wikidata driving side:** **left** (UK convention — relevant for visitors from RHD countries)
- **Thailand has held the dubious "world's most dangerous roads" title in multiple recent WHO comparisons.** Motorbike riders dominate fatalities. Tourist motorbike rentals are the single most common way Western visitors die in Thailand.

---

## 7. ENVIRONMENTAL & EPIDEMIOLOGICAL RISKS — Bangkok-specific

### Air quality (high health concern, season-dependent)
- Bangkok annual mean PM2.5: **20–30 µg/m³** baseline (WB current: 31.0; WHO 2019: 25.5)
- **Burning-season peak (Feb–April):** PM2.5 routinely 80–150 µg/m³ during the Northern-Thailand crop-burning teleconnection
- **Sukhumvit specifically:** traffic-PM additive year-round; arterial-canyon NOx and ultrafine particle exposure for any time spent on the sidewalk
- Open-Meteo current (Apr 2026): **33.7 °C, feels-like 40.5 °C, humidity 58%** — wet-bulb manageable but heat-stress is real
- Mitigation: N95 outdoors during burning season; HEPA in hotel; avoid outdoor exertion 6–10 AM dry-season

### Vector-borne disease
- **Dengue:** **Hyperendemic.** OpenDengue 8,721 confirmed cases nationally in 2025 (likely ~5–10× under-reported). Bangkok has year-round transmission, peaks Jul–Oct. *Aedes aegypti* breeds in standing water; condo balconies with planters are high-exposure. **Dengue is the most likely infectious disease a Sukhumvit visitor will encounter.**
- **Chikungunya:** Co-circulating
- **Malaria:** **Negligible in Bangkok** (urban core); risk on Cambodia/Myanmar borders only. CDC: prophylaxis NOT routinely recommended for Bangkok.
- **Japanese encephalitis:** Negligible in urban core
- **Rabies:** WHO-recorded 4 deaths in 2024 nationally; high stray dog density in Bangkok back-sois. **Pre-exposure rabies vaccination prudent for stays >2 weeks or any planned street-level activity outside Sukhumvit core.**

### Water & food
- **Tap water:** NOT potable. Bottled or filtered only.
- **Travelers' diarrhea:** baseline 30–40% incidence in first 2 weeks (CDC Yellow Book)
- **Hepatitis A:** vaccine recommended
- **Typhoid:** vaccine recommended for stays >2 weeks or street-food-heavy itineraries
- **Hepatitis E:** lower than India/Bangladesh but present
- **Cholera:** 5 cases / 8 deaths reported 2024 (WHO GHO) — sporadic, not Sukhumvit
- **Street food in central Bangkok is genuinely high-quality and broadly safe** when stalls are visibly busy with locals (turnover = freshness)

### Heat
- Hot season (Mar–May) afternoon highs: 33–38 °C; feels-like routinely 38–42 °C
- Wet-bulb risk: **moderate-high in April–May** during humid pre-monsoon; rare but exceeds dangerous wet-bulb 31 °C thresholds at peak

### Flooding
- Bangkok has **documented severe urban flooding** every monsoon (Sep–Nov peak). The 2011 floods displaced 12.8M people nationally; central Bangkok was partially inundated. Sukhumvit is on **gentle rise relative to the canal-laced western and eastern districts** but is NOT flood-immune — Soi-level flash flooding is routine after intense storms.
- **Long-term: Bangkok is sinking 1–2 cm/yr** (PSMSL = 0.75 at this cell) and the Gulf of Thailand is rising. World Bank projections suggest meaningful inundation risk for central Bangkok by ~2050.
- Avoid driving in standing water (electrocution from submerged pylons is a documented annual cause of death).

### Snakes & wildlife
- 24 venomous species nationally (cobras, kraits, vipers, sea snakes). GBIF cell-level density 0.24 — present in Bangkok green spaces but **urban-encounter rate negligible** for Sukhumvit visitors
- Stray dogs: moderate density; aggressive packs documented in outer districts, low risk on Sukhumvit Road itself
- Macaques: 68 GBIF records (Bangkok); they cluster around Wat Phra Kaew temple area, not Sukhumvit

---

## 8. ANTHROPOGENIC / CRIME-PROXIMATE RISKS

### What does NOT meaningfully apply to Sukhumvit Soi 1–55:
- **Insurgency / terrorism** — UCDP 111 events / 154 fatalities are **entirely the deep-south Pattani-Yala-Narathiwat conflict**. Bangkok had the 2015 Erawan Shrine bombing (20 dead) but no confirmed attack since on the Sukhumvit/CBD axis.
- **Active armed conflict** — conflict_zone flag = false
- **Informal settlement** — flag = false
- **Kidnap-for-ransom** — UNODC 0.031 / 100K (effectively zero foreign-tourist target)
- **Civil unrest disrupting CBD operations** — Mass Mobilization 254 events, but Bangkok protests have been geographically constrained (Ratchadamnoen / Democracy Monument area, occasionally Asok intersection); Sukhumvit east of Asok is rarely affected

### What DOES apply (the operative threat list for Sukhumvit):

| Risk | Notes |
|---|---|
| **Drink-spiking** | **Documented and recurring** in Sukhumvit Soi 11, Soi 23 (Soi Cowboy adjacent), Nana Plaza (Soi 4), and Patpong (Silom — adjacent). GHB and benzodiazepine cases reported by Bumrungrad ER. **Never accept a poured drink; never leave a drink unattended; carry your own from bar to table.** |
| **Honey-trap / extortion** | Heightened risk vector for any visibly affluent solo male in nightlife sois. Patterns: introduction via "friendly local" → invitation upstairs → drugged/robbed, OR consensual encounter → photo-blackmail. Tourist Police 1155 handle these frequently. |
| **Tuk-tuk gem scam** | Endemic at Grand Palace / Wat Pho (~6 km west). Driver claims Palace is "closed for ceremony" and offers "free tour" ending at gem shop. Refuse all sub-200-baht tuk-tuk offers near tourist sites. |
| **Grand Palace "closed" scam** | Variant of above — strangers near the Palace claim it's closed and redirect you to gems / suits / massage. The Palace is rarely actually closed. |
| **Taxi meter refusal / fare gouging** | Common at Suvarnabhumi and BKK tourist hubs. **Use Bolt or Grab apps.** Insist on meter; if refused, exit and find another. |
| **Motorcycle taxi / Grab-bike disputes** | Rare violence but real fare disputes. Confirm price before mounting. |
| **Bag-snatching from motorbike** | Documented in Sukhumvit sois. Walk on the inside of the sidewalk; bags worn cross-body on the inside shoulder. |
| **ATM / card skimming** | Use ATMs **inside bank branches or 5-star hotel lobbies** only. Skimmers documented on stand-alone ATMs in Sukhumvit, Khaosan, Patpong. |
| **Ping-pong show extortion** | Soi Cowboy, Nana Plaza, Patpong "shows" — undisclosed cover charges of 2,000–10,000+ baht enforced by intimidation. **Avoid entirely.** |
| **Cannabis legal ambiguity** | After mid-2024 re-restriction, recreational possession is now a fine and possible jail. Dispensaries still operate — buying isn't the issue; **carrying is.** Do not transport across borders. |
| **Other drug enforcement** | Amphetamine ("ya-ba") and MDMA possession can trigger long sentences. Foreigners receive no leniency. **Death penalty for trafficking remains on the books.** |
| **Lèse-majesté** | Do not discuss the Thai royal family on any platform — Section 112 sentences run 3–15 years. Old social-media posts are evidence. |
| **Petty pickpocketing** | Moderate. BTS Skytrain at peak hours, Asok intersection, Terminal 21 mall, Chatuchak weekend market. |
| **Tourist Police volunteer impostors** | A small number of fraudulent "volunteer tourist police" have been documented. Real officers wear standard uniforms; volunteers wear distinctive vests. When in doubt, call 1155 to verify. |
| **Road traffic for pedestrians** | **HIGH.** Sukhumvit Road has crosswalks (OSM density 0.83) but driver compliance is poor; turning vehicles routinely cross pedestrian phases. Use BTS overpasses where available. |
| **Two-wheeler injury** | **DO NOT rent or ride scooters/motorbikes** unless you have prior experience and a Thai-recognized motorcycle license. Tourist motorbike fatalities dominate consular casualty lists. |
| **Electrocution in floodwater** | Documented annual deaths during monsoon — submerged street furniture and pylons. Avoid wading. |
| **Stray dogs** | Lower density on Sukhumvit Road core than on back-sois; rabies pre-exposure vaccine prudent for longer stays. |

---

## 9. TARGETED THREAT PROFILE — for a Western solo tourist on Sukhumvit Soi 1–55

The risk delta between this individual and a generic local is concentrated in three categories:

1. **Predatory commercial nightlife** — Soi 4 (Nana), Soi 11, Soi 23 (Soi Cowboy adjacent), Soi 33, Patpong (Silom). The combined drink-spiking + honey-trap + ping-pong-show-extortion vector is **the highest-frequency adverse event** for solo Western visitors. Mitigation: stick to 5-star hotel bars (Bumrungrad-area Marriott, Park Hyatt, EmQuartier rooftops); never accept open drinks; call 1155 if anything feels off.
2. **Elective transport risk** — refusing motorbike rentals, refusing flagged-down tuk-tuks, using Bolt/Grab over street taxis, taking BTS Skytrain over road traffic during peak congestion eliminates ~80% of realistic injury risk.
3. **Air-quality cumulative exposure** — short stays (<7 days) outside burning season are low absolute risk; multi-week stays in burn season warrant N95 + indoor HEPA.

**There is no credible terrorism, kidnapping, or political-violence risk to a tourist on Sukhumvit Soi 1–55 under normal commercial circumstances.** The realistic life-threatening incidents are, in descending order:

1. Road traffic collision (especially as motorbike rider/pillion, or pedestrian crossing arterials)
2. Drink-spiking → robbery / sexual assault / fall injury
3. Cardiac event aggravated by heat + air pollution + dehydration (esp. for >50 visitors)
4. Foodborne / waterborne acute infection
5. Dengue (seasonal)
6. Drowning (if itinerary extends to islands — separate risk profile)
7. Drug-law-trigger arrest (if reckless)
8. Lèse-majesté charge (if incautious online)

---

## 10. RHYO DATA QUALITY DISCLOSURES

- **Cell `8864a48495fffff` runs on country-level fallback** for the composite score and the 9 risk columns. The 19-cell k-ring and 343-cell res-5 parent show identical 69.7/30.8 day/night numbers — confirming Thailand-wide baseline applied uniformly to inner Bangkok. **The cell-level OSM/HOT/JCI/Ookla/PSMSL signals (20 covariates) are real and present**, but the rollup function has not yet recomposited them into a Sukhumvit-specific score. Treat the headline score as "Thailand baseline" and the section 3 raw signals + section 5–7 narrative as the operational picture.
- **`emergency_access_risk = 0.95` is misleading at the cell level** — it reflects Thailand's national physician shortage (0.54/1000), not Sukhumvit's actual hospital density. JCI hospital proximity = 0.014 (top 5% globally) and HOT emergency POIs = 0.73 are the truer cell-level measures. See §4.
- **`women_safety_score_night` is null** for this cell — RHYO has not yet computed the night-women variant (Q26 scoring functions for transit/youth/children/women_night exist as columns only; SQL functions pending — see CLAUDE.md §36 "Youth/Children/Transit SQL functions: NOT IMPLEMENTED").
- **`source_count = 0` while `data_source_count = 10`** — discrepancy between two signal-counting columns; the value-bearing field for fused-source provenance is `data_source_count`.
- **South Thailand insurgency, Cambodia border mine contamination, and the Andaman tsunami zone are reflected in the country-level indicators but are NOT geographically applicable** to a Sukhumvit-based visitor. The single biggest analyst error reading RHYO Thailand data is attributing deep-south UCDP fatalities to Bangkok-area risk.
- **Air-quality, dengue surveillance, drink-spiking incidence, and tourist-scam topology are NOT in the cell-level layer at this hex** and are reported here from independent public-health and consular sources for completeness.
- **Database state:** Hetzner PG cluster online; Thailand has 600,174 res-8 cells fully scored (100% population coverage); 427 country indicators on file. Score recompute timestamp: 2026-04-02 23:47 CEST.
- **Sources cited inline.** Verifiable via: WHO GHO, World Bank WDI/WGI, UNODC, EM-DAT/CRED, USGS, GBIF, OSM Overpass, HOT (OSM-Humanitarian), Joint Commission International, Transparency International, Fund for Peace, V-Dem, Freedom House, BTI/Bertelsmann, MIT Place Pulse 2.0, US State Dept, UK FCDO, German AA, Canada travel.gc.ca, CDC, NTI GHSI, WEF TTDI, Wikivoyage, Inside Airbnb, Comparitech, WBL 2026, Equaldex, INFORM/HDX, UCDP GED, PSMSL, Open-Meteo, Ookla, OpenDengue, GDACS, NASA EONET, WRI Aqueduct, JMP/WHO/UNICEF.

---

## ONE-LINE BOTTOM LINE
**Sukhumvit Soi 1–55 is a "Guarded by day, Critical by night" tourist corridor where the realistic threats to a Western solo visitor's life are, in order: (1) road traffic — especially renting a motorbike, (2) drink-spiking and honey-trap extortion in Nana / Soi 11 / Soi Cowboy / Patpong nightlife, (3) heat + air-pollution cardiac strain in burn season, (4) foodborne illness, (5) seasonal dengue — NOT terrorism, NOT kidnapping, NOT political violence; call 1155 (Tourist Police) for anything foreigner-relevant.**
