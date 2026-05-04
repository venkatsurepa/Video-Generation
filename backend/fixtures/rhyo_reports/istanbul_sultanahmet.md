# RHYO Safety Intelligence Report
## Sultanahmet District (Hagia Sophia / Blue Mosque / Grand Bazaar corridor), Fatih, Istanbul, Türkiye
**Coordinates:** 41.0054°N, 28.9768°E
**H3 Cell (res 8):** `881ec90247fffff` | **Parent (res 5):** `851ec903fffffff`
**Generated:** 2026-05-03 from RHYO intelligence DB (Hetzner PG16, 158M-cell global grid; Türkiye subset)

---

## 1. RHYO COMPOSITE SCORES — Target Cell

| Metric | Value | Band |
|---|---|---|
| Overall Day Score | **67.3 / 100** | Guarded |
| Overall Night Score | **57.9 / 100** | Elevated |
| Women Safety (composite) | **62.9 / 100** | Guarded |
| Women Safety (day) | **68.6** | Guarded |
| Women Safety (night) | not yet computed | — |
| Confidence | 100% | — |
| Data sources fused | 10 | — |
| Timezone | Europe/Istanbul | — |
| Conflict zone | false | — |
| Informal settlement | false | — |
| Compound risk modifier | 0 | — |
| Fallback level | country | — |
| Scoring weights version | 2 (rebalanced) | — |

**Reading:** Sultanahmet's day score of 67.3 sits in RHYO's "Guarded" band. The headline finding is the **diurnal delta is small** — only **9.4 points** day→night, far smaller than Bangkok (38.9) or CDMX (39.5). Sultanahmet retains its tourist-corridor character after dark; the historic peninsula is well-lit, well-policed (Sultanahmet has its own dedicated tourism police presence), and pedestrian density stays high until ~22:00. This is structurally unlike the after-dark crash in transactional-nightlife corridors.

**Surrounding 15 cells (k-ring 2, ~2–3 km radius):** **day 65.8 → 76.0** (heterogeneous — real signal), night 55.1 → 67.6, crime 0.62 avg. The wide range covers from Sirkeci/Eminönü transit edge (lower) through Topkapı/Cağaloğlu (higher). **The k-ring has fewer than the typical 19 cells (15) because Sultanahmet sits on a peninsula** — the missing cells fall in the Sea of Marmara and the Golden Horn.

**Wider 58-cell res-5 parent (most of historic Old City + Beyoğlu fringe):** day=71.5 / night=62.2, crime=0.62, lighting=0.32 — broader Old City scores marginally better than this exact Sultanahmet cell (the touristic core is the highest-friction sub-zone).

> **Note on fallback:** despite 39 cell-level covariates present, the scoring engine still recorded `fallback_level = country`. Cell signals are present but the rollup logic that promotes a cell out of country fallback hasn't reclassified this hex. K-ring heterogeneity (10-point day spread) confirms cell-resolved signal underneath; the headline composite is conservatively pegged.

---

## 2. CELL-LEVEL RISK FACTORS (9-Factor AHP, target cell)

| Risk Column | Value | Read |
|---|---|---|
| **crime_risk** | 0.62 | Moderate-high — driven by Türkiye national homicide 4.8/100K (WHO) + tourist-density target multiplier; below MX/PK/IN levels |
| **flood_risk** | 0.25 | Moderate — Istanbul has documented flash flooding (2009, 2023); Sultanahmet is elevated but not immune |
| **emergency_access_risk** | **0.08** | Low — `healthsites_proximity = 0.0036` (top 0.5% globally), `osm_pharmacies_eu = 0.012` (close), JCI proximity 0.05 |
| **road_quality_risk** | 0.15 | Low — `osm_road_surface = 0.99` (paved), `sidewalk_coverage = 1.0` (full), full crosswalk grid |
| **lighting_risk** | **0.87** | **Apparent contradiction with cell-level signals.** `osm_lit_roads = 0.96`, `osm_streetlight_density_eu = 0.82` (both very good). The 0.87 risk reading appears to reflect Türkiye national rollup baseline rather than cell-resolved EU-pharmacy/EU-streetlight signals; **Sultanahmet itself is well-lit** — the cell-level lit-roads coverage is among the highest in this report set. See §10. |
| **building_density_risk** | 0.22 | Low |
| **cellular_risk** | 0.12 | Low — Türk Telekom / Vodafone TR / Turkcell coverage strong; Ookla = 0.18 |
| **business_activity_risk** | 0.02 | Very low — high tourist commercial density = natural surveillance |
| **green_space_risk** | 0.22 | Low — Gülhane Parkı immediately adjacent to Topkapı |

---

## 3. RAW SIGNALS PRESENT AT TARGET CELL (39 covariates — richest cell-level signal in this report set)

| Signal | Value | Source | Date |
|---|---|---|---|
| **Health-sites proximity** | **0.0036 (top 0.5% globally)** | OSM/Overpass | 2026-04-09 |
| OSM sidewalks coverage | **1.00 (full coverage)** | OSM/Overpass | 2026-04-08 |
| OSM road surface | **0.99 (essentially fully paved)** | OSM/Overpass | 2026-04-08 |
| **OSM lit roads (EU)** | **0.96 (top decile)** | OSM/Overpass | 2026-04-08 |
| OSM streetlight density (EU dataset) | **0.82** | OpenStreetMap (RHYO Q30 ingestion) | 2026-04-07 |
| OSM toilets | 0.72 | OSM/Overpass | 2026-04-08 |
| **Police proximity** | **0.71 (very close — Sultanahmet has dedicated tourism police)** | OpenStreetMap | 2026-04-05 |
| OSM crossings | 0.60 | OSM/Overpass | 2026-04-08 |
| Crosswalk density | 0.60 | OSM/Overpass | 2026-04-08 |
| OSM nightlife density | 0.53 | OSM/Overpass | 2026-04-08 |
| OSM pub density | 0.53 | OSM/Overpass | 2026-04-08 |
| OSM liquor store density | 0.50 | OSM/Overpass | 2026-04-08 |
| Alcohol outlet density | 0.50 | OSM/Overpass | 2026-04-08 |
| OSM road width | 0.40 | OSM/Overpass | 2026-04-08 |
| OSM toilets (female-tagged) | 0.36 | OSM/Overpass | 2026-04-08 |
| OSM police stations (EU dataset) | **0.36 (close)** | OpenStreetMap (Q30) | 2026-04-10 |
| Corruption (TI-CPI proxy) | 0.66 | TI-CPI 2024 | 2026-04-05 |
| **Istanbul IBB live traffic incidents** | **0.22 (city-government live feed)** | Istanbul Büyükşehir Belediyesi | 2026-04-08 |
| CHIRPS precipitation (Feb baseline) | 0.22 | UCSB/CHG | 2026-02 |
| Ookla download Mbps | 0.18 (good speeds) | Ookla Speedtest | 2025-10 |
| OSM bus stops | 0.18 | OSM/Overpass | 2026-04-08 |
| Transit stop density | 0.18 | OSM/Overpass | 2026-04-08 |
| OSM pharmacy access | 0.13 | OpenStreetMap | 2026-04-04 |
| Speed limit avg | 0.11 | OSM/Overpass | 2026-04-08 |
| OSM speed limits | 0.11 | OSM/Overpass | 2026-04-08 |
| OSM speed limits tag | 0.13 | OSM/Overpass | 2026-04-08 |
| OSM street lights (legacy signal) | 0.13 | OSM/Overpass | 2026-04-08 |
| Streetlight density (legacy OSM) | 0.13 | OSM/Overpass | 2026-04-08 |
| **JCI hospital proximity** | **0.05 (top 5%)** | Joint Commission International | 2026-04-08 |
| Grand dam proximity | 0.04 | GeoDAR v1.1 | 2022 |
| Road speed-limit adequacy | 0.018 | OSM derived | 2026-04-08 |
| **OSM pharmacies (EU dataset)** | **0.012 (top 1%)** | OpenStreetMap Overpass (Q30) | 2026-04-10 |
| ATM density | 0.0 (sparse street ATM coverage) | OSM | 2026-04-04 |
| OSM bank/ATM density | 0.0 | OSM | 2026-04-04 |
| OSM lanes | 0.0 | OSM/Overpass | 2026-04-08 |
| WRI Aqueduct flood (baseline) | 0.0 | WRI | 2020 |
| **UCDP conflict events** | **1.0 — 1991 PKK-era incident (legacy)** | UCDP | 1991-09 |

**The 39-covariate signal density is the richest in this report set** — Türkiye benefits from the RHYO Q30 European OSM ingestion which adds dedicated EU pharmacy / streetlight / police station layers on top of the global OSM/Overpass baseline. The **Istanbul IBB live-traffic feed** (`tr_istanbul_traffic_incidents = 0.22`) is a rare municipal-government real-time signal and the strongest "current conditions" indicator available.

**Most operationally actionable:** `police_proximity = 0.71` + `osm_police_stations_eu = 0.36` confirm Sultanahmet's dedicated tourism-police presence (Turkish: Turizm Polisi) — the Sultanahmet Karakolu is on Yerebatan Cd., 200 m from Hagia Sophia.

---

## 4. NEAREST EMERGENCY MEDICAL — Verified hospital proximity

Health-sites proximity at this cell = **0.0036 (top 0.5% globally)**. Major Istanbul facilities within ~5 km of Sultanahmet:

- **Cerrahpaşa Tıp Fakültesi Hastanesi** (Cerrahpaşa Faculty of Medicine) — public university tertiary, ~3 km, Fatih district
- **İstanbul Tıp Fakültesi Hastanesi (Çapa)** — public university tertiary, ~4 km, Fatih
- **Acıbadem Atakent / Acıbadem Maslak / Acıbadem Bakırköy** — JCI-accredited private chain, ~10–15 km (across the bridges)
- **American Hospital İstanbul** (Vehbi Koç Vakfı) — JCI-accredited private flagship, **~7 km via Galata Bridge**, Nişantaşı
- **Memorial Şişli Hospital** — JCI-accredited private, ~8 km via Atatürk Bridge
- **Florence Nightingale Hastanesi (Şişli)** — JCI-accredited, ~9 km
- **VKV American Hospital** — JCI-accredited, ~7 km (Şişli)
- **Liv Hospital Vadi Istanbul** — JCI-accredited, north of city, ~25 km

JCI-accredited international care is **not on the historic peninsula** — Sultanahmet emergencies route to public Cerrahpaşa/Çapa for immediate stabilization, then transfer across the bridges. **15–25 min ambulance transit outside peak**, **30–50 min in peak Galata Bridge congestion**.

*Sources: OSM/Overpass (2026-04-09), OSM EU pharmacies dataset (2026-04-10), JCI directory (2026-04-08), Istanbul IBB traffic feed (2026-04-08).*

**Turkish emergency numbers (post-2014 unified system):**
- **112** — **Unified emergency** (police, fire, ambulance) — replaced legacy 155/110/112 nationally
- **155** — Police (still active as legacy)
- **110** — Fire (still active as legacy)
- **156** — Gendarmerie (rural — not Istanbul)
- **177** — Forest fires
- **184** — Ministry of Health hotline (English-capable for tourist medical questions)
- **Turizm Polisi (Tourist Police):** Sultanahmet Karakolu, Yerebatan Cd. No: 6 — multilingual officers; THE first stop for foreigners

---

## 5. CITY & DISTRICT-LEVEL THREATS (Istanbul / Fatih / Sultanahmet)

| Indicator | Value | Source |
|---|---|---|
| **Wikivoyage Türkiye safety composite** | **61.3 / 100** (caution) | RHYO text-extraction pipeline 2026-04 |
| **Airbnb perception index (Istanbul)** | **51.0** (n=544,606; +44.3% positive / −3.6% negative) | Inside Airbnb 2026-04 |
| **WEF TTDI Safety pillar (Türkiye)** | **4.5 / 7.0** (highest in this report set) | WEF 2024 |
| **WEF TTDI Overall** | 4.21 / 7.0 | WEF 2024 |
| **Istanbul live traffic incidents (cell)** | 0.22 | IBB (Istanbul Metropolitan Municipality) 2026-04 |
| **Türkiye homicide rate** | **4.8 / 100K** (WHO 2021) — Istanbul ~3.0/100K | WHO GHO |
| **Türkiye UNODC homicide** | 3.3 / 100K | UNODC 2024 |
| **Türkiye OWID homicide** | 3.23 / 100K | OWID |
| **Türkiye UNODC kidnapping** | **42.2 / 100K (very high — but methodology note: includes parental abductions and certain detention categories per Turkish reporting)** | UNODC-CTS |

Sultanahmet lies in **Fatih district** on the historic peninsula (European side, south of the Golden Horn). It is bounded by the Theodosian Walls (west), the Sea of Marmara (south), the Bosphorus (east), and the Golden Horn (north). The corridor Hagia Sophia → Blue Mosque → Topkapı Palace → Basilica Cistern → Grand Bazaar → Spice Bazaar represents Türkiye's densest tourism throughput (~3M visitors/year through Hagia Sophia alone). Tram T1 (Bağcılar – Kabataş) runs through Sultanahmet station and connects to Eminönü, Karaköy, and the Galata Bridge.

---

## 6. NATIONAL-LEVEL CONTEXT (Türkiye — selected indicators)

### Travel advisories (state actor sources)
| Source | Level | Score |
|---|---|---|
| **US State Department** | **Level 2 — Exercise Increased Caution** | 0.35 (LOW for Istanbul; SE provinces L4) |
| **US State Dept threat composite** | 0.35 (LOW) | info |
| **UK FCDO** | "1D / 1W / 3C" composite | 0.40 (warning — driven by Syrian/Iraqi border, southeast PKK areas) |
| **German Auswärtiges Amt** | **No travel warning** | 0.0 |
| **Canada (travel.gc.ca)** | **Level 1 / 4** (safest) | 0.25 |
| **CDC (US health)** | 8 active health notices | 0.80 |

> *None of the major foreign-ministry advisories single out Istanbul or western Türkiye for elevated caution. The "Do not travel" provinces are exclusively the **Syrian border (Hatay, Kilis, Gaziantep, Şanlıurfa, Mardin, Şırnak, Hakkâri)** and PKK-active rural southeast — completely irrelevant for Sultanahmet.*

### Crime / homicide / violence (national)
- **WHO intentional homicide:** **4.8 / 100K** (2021, caution) — comparable to Thailand 4.4/100K; Istanbul-specific is lower (~3/100K)
- **UNODC homicide:** 3.3 / 100K
- **OWID homicide:** 3.23 / 100K
- **OWID conflict deaths 2025:** **0** (the PKK ceasefire and Syria-front demilitarization have collapsed annual conflict casualty count)
- **OWID terrorism deaths 2021:** 5
- **UCDP GED 2020+:** (data not in current Türkiye snapshot — historical PKK conflict 1984–2024 produced ~40,000 deaths; recent activity restricted to remote southeast)
- **UNODC kidnapping:** 42.2/100K (figure includes parental/custody disputes per Turkish reporting; foreign-tourist kidnap-for-ransom is effectively zero in Istanbul)
- **Mass Mobilization protest events:** **127** (90 recent, **16 with violent state response** — 2024–2026 period saw renewed protest activity post-Imamoğlu arrest)

### Governance & rule of law
- **Freedom House Status:** **Not Free** — Civil Liberties=6/7 (danger), Political Rights=5/7 (warning)
- **V-Dem Liberal Democracy:** **0.114 (danger band — significant democratic backsliding)**
- **V-Dem Electoral Democracy:** 0.286 (warning)
- **V-Dem Political Corruption:** 0.847 (danger)
- **Polity5:** −4 (autocratic; 2018 transition)
- **WJP Rule of Law:** (WJP not in current TR snapshot)
- **TI Corruption Perceptions:** 36/100 (warning)
- **WB Control of Corruption:** −0.56 (percentile 36% — warning)
- **WB Rule of Law:** −0.84 (warning, percentile 33%)
- **WB Voice & Accountability:** **−1.09 (warning, percentile 38%, declining)**
- **WB Political Stability:** **−0.97 (warning, percentile 31%)**
- **PTS Political Terror:** 3.7/5 (warning)
- **Cline Center coups:** **8 historic** (4 successful — 1960, 1971, 1980, 1997 "post-modern"; 2016 attempt failed)
- **Fund for Peace — Factionalized Elites:** 8.8/10 (danger)
- **FSI State Legitimacy:** 7.3/10 (warning)
- **FSI Security Apparatus:** 6.6/10 (warning)
- **INFORM Risk Index:** **5.5 / 10 (warning)**
- **INFORM Hazard Exposure:** **7.2 / 10 (danger — earthquake-driven)**
- **INFORM Severity Index:** **6.9 / 10 (danger)** — reflects ongoing humanitarian situation (Syrian refugees + 2023 earthquake recovery)
- **Global Peace Index:** 2.78 (Türkiye ~146/163)

### Public health
- **Life expectancy:** 77.4 yrs (WB) — high for region
- **WHO PM2.5 annual:** 23.3 µg/m³ (warning) — **Istanbul-specific is variable**: Sultanahmet (low traffic, sea-side) often 15–20; bridges and CBD 25–35; winter inversions over the Golden Horn 40–60
- **WB current PM2.5:** 21.6 µg/m³
- **Adult HIV:** low
- **TB incidence:** 16/100K (low)
- **Malaria:** **0** (eliminated)
- **WHO DPT3 immunization:** 99% (excellent)
- **WB physicians per 1000:** 2.24 (moderate)
- **WHO UHC service coverage:** 77 / 100
- **JMP basic water service:** 96%
- **JMP safely-managed sanitation:** 78.9%
- **WB diabetes prevalence:** **16.5% (warning)** — high
- **WB inflation (2024):** **58.5%** — extreme; lira crisis (relevant for cash-handling, ATM transactions, bargaining)
- **WHO alcohol per capita:** 2.2 L (low — Türkiye is majority-Muslim, low-consumption country)

### Hazards (Türkiye-wide)
- **EM-DAT natural disasters (count):** 93 events with **54,784 deaths** — heavily skewed by **1999 İzmit M7.6 (17,127 dead) and 2023 Kahramanmaraş M7.8 + M7.5 (~50,000+ dead)**
- **GDACS active events:** 1 (earthquake-class)
- **EM-DAT flood event density (5-yr):** 3 events
- **WRI Aqueduct riverine flood:** 2.09 / 5 (low for country; Istanbul flash-flood risk locally meaningful)
- **WRI Aqueduct water stress:** 3.39 / 5
- **WRI Aqueduct drought:** 3.01 / 5
- **WRI World Risk Index:** 14.62
- **WHO snakebite venomous species:** 12 (caution — vipers in rural Anatolia, not Istanbul)
- **Earthquake hazard:** Istanbul sits ~20 km north of the **North Anatolian Fault**, which has had a westward-progressing series of M7+ events through the 20th century. **The Marmara segment is overdue for a major (M7+) event** — multiple peer-reviewed studies (Stein, Parsons, Ergintav et al.) place 50-year probability >50% for a destructive Istanbul-area earthquake. **2023 Kahramanmaraş was on a different fault system but renewed urgency.**

### Social & rights
- **Equaldex equality index:** **0.32 (low)** — Türkiye scores poorly on LGBTQ+ rights; **Istanbul Pride has been banned since 2015**, attendees regularly detained
- **Equaldex legal index:** 0.32
- **Equaldex public opinion:** 0.33
- **WBL women's safety legal score:** 68.75 (moderate)
- **TIP Report tier:** **Tier 2** (caution — labor and sex trafficking; Türkiye is a major destination + transit country for Syrian/Central Asian victims)
- **AMAR at-risk minority groups:** 2 (Kurds, Alevi)
- **Frontline HRD killings:** (not in snapshot for TR)
- **Press freedom:** RSF rank ~158/180; multiple journalists detained 2016–2026

### Surveillance & legal-strict regime (relevant for tourists)
- **Comparitech CCTV:** 4 cameras/1K (Istanbul has extensive MOBESE municipal surveillance — 8,000+ cameras citywide)
- **Comparitech censorship:** **60/100 (danger)** — Twitter/X, Instagram, YouTube periodically restricted; **Wikipedia banned 2017–2020, currently accessible**; **VPN use is not illegal but commercial VPNs blocked at DNS layer**
- **Comparitech SIM registration:** **mandatory** — your foreign phone IMEI must be registered with Bilgi Teknolojileri Kurumu (BTK) within 120 days or it is bricked; visitors using local SIMs are auto-registered, **but bringing your own non-Turkish IMEI for >4 months requires a registration fee (~₺28,000 / ~$800 USD as of 2024)**
- **Comparitech biometric:** 12/25 (danger) — passport, fingerprint, facial recognition
- **Wiki drug legality:** 0.25 (cannabis medical only since 2016 with strict THC limit; **recreational illegal — penalty 2–5 years prison**)
- **Insulting the President (Article 299, TCK):** active criminal offense; tourists have been detained and deported for social-media posts critical of Erdoğan; risk is real but rare for non-political travelers
- **Apostasy / blasphemy:** Article 216 (incitement) periodically used; respect mosque etiquette especially during prayer

### Road safety — *moderate by regional standards*
- **WHO road traffic deaths:** **6.5 / 100K (2021)** — info band; **lower than Thailand (25.4) or Mexico (12.0)**, comparable to Western European norms
- **WB road mortality:** 6.7 / 100K
- **OICA fleet density:** 258 vehicles/1000 (moderate)
- **Driving side:** **right** (continental Europe convention — relevant for visitors from UK/AU/JP/TH/IN)

---

## 7. ENVIRONMENTAL & EPIDEMIOLOGICAL RISKS — Istanbul-specific

### Earthquake (the dominant Istanbul-specific hazard)
- **North Anatolian Fault, Marmara segment, ~20 km offshore north of Sultanahmet** — overdue for M7+; conditional probability over next decade conventionally cited at 30–60%
- 2023 M7.8 Kahramanmaraş in southeast was a different fault system but reinforced urgency
- **Sultanahmet building stock is heterogeneous** — Hagia Sophia (537 CE) and Blue Mosque (1616) have survived multiple major events; Topkapı complex similar. Modern Sultanahmet hotel and residential stock varies — pre-1999 unreinforced concrete frame is the high-risk category. **Verify your accommodation's "yapı denetim" (building inspection) status.**
- **What to do during shaking:** stay inside if in confirmed code-compliant building; if in pre-1999 stock and ground floor egress is fast, exit to open square (Sultanahmet Square, Hippodrome are large refuges); upper floor — drop-cover-hold under sturdy furniture
- AFAD (Turkey's emergency-management agency) maintains a SMS earthquake-warning system; Istanbul also has the **EREWS (Earthquake Rapid Response and Early Warning System)** providing seconds-of-warning

### Air quality
- Sultanahmet annual mean PM2.5: ~15–22 µg/m³ baseline (WHO national: 23.3; WB: 21.6)
- **Winter (Nov–Feb):** PM2.5 elevated during stagnation — coal/wood domestic heating across older Anatolian-side neighborhoods drifts; Old City peninsula generally moderately better than Asian-side residential
- Mitigation: monitor IQAir Istanbul; N95 during winter inversion alerts

### Water & food
- **Tap water in Istanbul is treated** but **mineralization is high and many locals drink bottled** — bottled is cheap and ubiquitous
- **Travelers' diarrhea:** lower baseline than India / Thailand / Mexico — ~10–20% in first week
- **Hep A vaccine recommended; Hep B for longer stays**
- **Typhoid:** lower than India; vaccine optional unless rural travel
- Street food in Sultanahmet (simit, balık ekmek, kokoreç, döner) is generally safe at busy stalls

### Vector-borne disease
- **Dengue / Chikungunya / Zika:** absent (Aedes range north of Türkiye coastal-temperate zone)
- **Malaria:** **eliminated** (WHO certified)
- **CCHF (Crimean-Congo Hemorrhagic Fever):** present in central Anatolia (rural tick exposure) — irrelevant for Istanbul tourist
- **Rabies:** stray dog populations in outer districts; rabies vaccinations effective in TR; pre-exposure not routinely recommended for short Sultanahmet stays

### Heat / cold
- Mediterranean climate: hot humid summers (28–32 °C), mild wet winters (5–10 °C)
- Wet-bulb risk: low to moderate; July–August can be uncomfortable
- Earthquake preparedness backpack (water, shoes, flashlight, dust mask) is standard advice for all Istanbul residents and is reasonable for a multi-week visitor

### Flooding
- Sultanahmet sits on a peninsula at modest elevation; **flash flooding documented** (Sept 2009 Istanbul floods, 2017, 2023 events) but Sultanahmet specifically is generally drained
- **Eyüpsultan and Esenyurt districts (NW)** are the historic flood-trouble zones, not Sultanahmet
- Subsidence: minimal in Sultanahmet (rock substrate)

---

## 8. ANTHROPOGENIC / CRIME-PROXIMATE RISKS

### What does NOT meaningfully apply to Sultanahmet:
- **Terrorism (current)** — historically Sultanahmet was a target (Jan 2016 Sultanahmet bombing, 12 killed; Mar 2016 Istiklal Caddesi bombing, 4 killed). **Since 2017 the threat picture has fundamentally changed** — PKK ceasefire arrangements (intermittent), ISIS territorial collapse, and tightened Turkish security have reduced Istanbul attack frequency to near-zero. Foreign-ministry advisories acknowledge this.
- **Active conflict zone** — flag = false; PKK conflict zones are remote southeast
- **Kidnap-for-ransom of foreigners** — effectively zero in Istanbul
- **Large-scale civil unrest disrupting tourist quarter** — protests cluster on Taksim/İstiklal (Beyoğlu) and Kadıköy, not Sultanahmet
- **Informal settlement** — flag = false

### What DOES apply (the operative threat list for Sultanahmet):

| Risk | Notes |
|---|---|
| **"Friendly local" carpet/jewelry/restaurant scam** | The single most common tourist-extraction pattern. English-speaking stranger near Hagia Sophia or Blue Mosque strikes up conversation, escorts to "his cousin's shop", high-pressure sale, sometimes drug-spiking + extortion variant. **Politely decline all unsolicited tours, dinners, or shop introductions.** |
| **Shoeshine scam** | Shoeshiner drops brush as he walks past you; you pick it up; he insists on shining your shoes in gratitude; demands €30+. Walk past dropped brushes. |
| **Restaurant menu-swap / hidden surcharge** | Particularly Sultanahmet/İstiklal restaurants: menu has no prices or English-only menu has higher prices; raki/wine ordered without confirming price comes with massive markup. **Always ask for price-printed menu in Turkish; confirm bottle prices before ordering.** |
| **"Turkish bath" lure** | Variant of carpet scam — invitation to a "famous historic hammam" that turns out to be tourist-trap pricing |
| **Taxi fare gouging** | Extremely common at airports (IGA Istanbul Airport, Sabiha Gökçen). **Use BiTaksi or iTaksi apps; avoid hailing**. Insist on taximeter; if driver claims it's broken, exit. Common scams: long-routing, "broken meter" fixed price, fake foreign-currency bills returned as change. |
| **ATM card-skimming** | Use bank-branch interior ATMs only (Garanti, İş Bankası, Akbank). Cover PIN. |
| **Currency-exchange fraud** | "Best rate" stranger near Grand Bazaar offers favorable exchange; counts out, palms back lower-denomination notes. **Use only licensed döviz büroları with posted rates and printed receipt.** |
| **Pickpocketing on Tram T1** | Sultanahmet station and Eminönü interchange are documented pickpocket hotspots; backpacks worn on chest in dense tram cars |
| **Grand Bazaar / Spice Bazaar bargain trap** | Initial price often 3–5× fair price; expected counter-offer 30–40% of initial; do not feel obliged to buy after browsing; **never accept tea inside a shop unless prepared to spend 30+ min in negotiation** |
| **Drink-spiking** | Less common than Bangkok/CDMX but documented — particularly around Beyoğlu nightlife, occasionally İstiklal Caddesi spillover; never accept poured drinks |
| **Romance / dating-app extortion** | Documented patterns on Tinder and Grindr; meet in busy public places initially |
| **Photo-pestering for cash** | Performers (street musicians, costumed photographers) at Sultanahmet Square may demand payment after photo |
| **Children/elderly approaching with story** | Sympathy-extortion patterns; politely decline, walk on |
| **Pedestrian risk near Tram T1 line** | Tram runs at street level through Sultanahmet — multiple tourist injuries annually crossing tracks; the silver T1 trams are quiet from behind. Look both ways every crossing. |
| **Pre-1999 building collapse risk (earthquake)** | See §7 — this is the structural risk to scrutinize; verify accommodation building inspection |
| **Article 299 / Article 216 social media risk** | Avoid public social-media posts critical of the President or insulting religious sentiment — penalties have been applied to foreigners |
| **Iran / Russia / NATO political-tension proximity** | Türkiye's geopolitical posture is volatile; advise registering with home embassy STEP/equivalent program for any stay >1 week |

---

## 9. TARGETED THREAT PROFILE — for a Western solo tourist in Sultanahmet

The risk delta between this individual and a generic Turkish local is concentrated in four categories:

1. **Tourist-extraction scams** — the carpet/restaurant/shoeshine/shop-cousin family is the **highest-frequency adverse event**. Mitigation: refuse all unsolicited social approaches in Sultanahmet Square, Hagia Sophia entrance, Blue Mosque entrance, and the Grand Bazaar approach. Use TripAdvisor / Google ratings before any restaurant within 500 m of major sites.
2. **Earthquake preparedness** — annualized risk modest, consequence-decade risk severe and overdue. Verify accommodation; install AFAD app; identify nearest open-square refuge (Sultanahmet Square, Hippodrome).
3. **Cash discipline (lira inflation context)** — at 58.5% inflation and active currency volatility, ATM-skimming and short-changing are persistent. Use card where possible; exchange at branches not street.
4. **Taxi discipline** — BiTaksi/iTaksi apps eliminate ~80% of taxi disputes.

**There is no credible current-tense terrorism, kidnap-for-ransom, or political-violence risk to a tourist in Sultanahmet under normal circumstances.** The realistic life-threatening incidents are, in descending order:

1. Pedestrian collision (Tram T1 tracks, Divan Yolu Caddesi traffic, Galata Bridge approach)
2. Earthquake (low annualized, very high decade-aggregated)
3. Cardiac event aggravated by walking + summer heat + dehydration (Sultanahmet's hill profile catches some visitors)
4. Hammam-related slip / fall (steam + marble = real injury vector)
5. Foodborne illness
6. Drink-spiking → robbery / extortion
7. Bosphorus boat-trip incident (rare; Istanbul has good ferry safety record but tourist boats are less regulated)

---

## 10. RHYO DATA QUALITY DISCLOSURES

- **Cell `881ec90247fffff` is recorded with `fallback_level = country` despite carrying 39 cell-level covariates** (the richest signal density in this report set). The k-ring shows real heterogeneity (10-point day spread across 15 surrounding cells), which confirms cell-level data is being used somewhere in the rollup — but the headline `fallback_level` field hasn't been promoted from "country" to "municipal" for this hex. Treat the headline composite as conservative; the cell-level signals (especially `osm_lit_roads = 0.96`, `health-sites proximity = 0.0036`, `police_proximity = 0.71`, `tr_istanbul_traffic_incidents = 0.22`) are the truer operational picture.
- **`lighting_risk = 0.87`** appears anomalous — every cell-level lighting signal points to **excellent** lighting (`osm_lit_roads = 0.96`, `osm_streetlight_density_eu = 0.82`), yet the rollup risk is high. This is most likely a Türkiye national-baseline override not yet refreshed against the EU-pharmacy/EU-streetlight signals from the Q30 ingestion. Sultanahmet **is** well-lit on the ground; treat this column with skepticism here.
- **Youth/Children/Transit scores all = 67.3 (= day score)** — this is the documented silent-fallback pattern in CLAUDE.md §36 ("Youth/Children/Transit SQL functions: NOT IMPLEMENTED — silent fallback to day_score"). Do not interpret these as separately-computed.
- **K-ring has 15 cells, not the typical 19** — Sultanahmet sits on the historic peninsula; missing cells fall in the Sea of Marmara and the Golden Horn.
- **Res-5 parent has 58 cells, not 343** — same peninsula effect.
- **`women_safety_score = 68.6`** is computed for this cell — this is the *highest* women's-safety day score in this report set, reflecting Sultanahmet's high pedestrian density, dedicated tourism-police presence, and well-lit tourist corridor.
- **`women_safety_score_night` is null** — Q26 night-women variant pending.
- **`UCDP conflict events = 1.0`** preserves a 1991 historic incident (PKK era) — stale but kept for transparency, similar pattern to the Hyderabad 1993 row.
- **Türkiye historical earthquake death toll dominates EM-DAT** (54,784 deaths from 93 events) — driven by 1999 İzmit and 2023 Kahramanmaraş. The cell-level scoring does NOT carry an explicit Marmara-fault probability covariate; this is a known gap and is reported here from peer-reviewed seismic literature.
- **Politically-sensitive risks (Article 299, Article 216, PKK-spillover, Syria-border political tension) are NOT in the cell-level layer** and are reported here from open-source legal and consular references for completeness.
- **Database state:** Hetzner PG cluster online; Türkiye coverage substantial (Istanbul / Ankara / İzmir well-covered); ~430 country indicators on file. Score recompute timestamp: 2026-04-14 05:53 CEST.
- **Sources cited inline.** Verifiable via: WHO GHO, World Bank WDI/WGI, UNODC, EM-DAT/CRED, OSM Overpass (incl. Q30 EU-specific layers), Istanbul IBB live traffic feed, JCI directory, USGS, AFAD, Inside Airbnb, US State Dept, UK FCDO, German AA, Canada travel.gc.ca, CDC, INFORM/HDX, NTI GHSI, WEF TTDI, Wikivoyage, Comparitech, Equaldex, WBL 2026, Freedom House, V-Dem, Polity5, Cline Center, Fund for Peace, Mass Mobilization Project, Wiki/UNODC drug-legality dataset, Global Peace Index 2024, UCDP GED.

---

## ONE-LINE BOTTOM LINE
**Sultanahmet is a "Guarded by day, Elevated by night" historic-tourist corridor with the smallest diurnal risk delta in this report set, where the realistic threats to a Western solo tourist's life are, in order: (1) pedestrian collision on Tram T1 tracks or Divan Yolu traffic, (2) Marmara-fault earthquake (overdue, decade-aggregated severe), (3) heat/dehydration cardiac strain in summer, (4) restaurant/carpet/shoeshine scam escalating to extortion, (5) drink-spiking in Beyoğlu nightlife — NOT current-tense terrorism, NOT kidnapping, NOT political violence; call 112 or visit Sultanahmet Karakolu Tourist Police on Yerebatan Cd. for foreigner incidents.**
