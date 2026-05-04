# RHYO Safety Intelligence Report
## Alfama district (Castelo de São Jorge / Sé de Lisboa / Tram 28 corridor), Santa Maria Maior, Lisbon, Portugal
**Coordinates:** 38.7117°N, −9.1304°W
**H3 Cell (res 8):** `8839336765fffff` (target cell — **not in safety_scores; see §10**) | **Parent (res 5):** `85393367fffffff` | **Proxy cell (same parent):** `8839336695fffff`
**Generated:** 2026-05-03 from RHYO intelligence DB (Hetzner PG16, 158M-cell global grid; Portugal subset 115,077 res-8 cells)

---

## 1. RHYO COMPOSITE SCORES — Target cell context

| Metric | Value | Band |
|---|---|---|
| Overall Day Score | **83.7 / 100** | **Clear** |
| Overall Night Score | **83.7 / 100** | **Clear** |
| Women Safety (composite) | **83.7 / 100** | **Clear** |
| Women Safety (night) | not yet computed | — |
| Confidence | 100% | — |
| Data sources fused | 0 (per row) | — |
| Timezone | Europe/Lisbon | — |
| Conflict zone | false | — |
| Informal settlement | false | — |
| Compound risk modifier | 0 | — |
| Fallback level | **country** | — |

**Reading:** Lisbon scores in RHYO's **"Clear"** band — the highest of the five reports in this set, and the only one where day and night scores are equal. This reflects Portugal's structural baseline: WHO homicide 0.83/100K (one of the lowest globally), Global Peace Index 1.37 (top 10), Polity5 +10 (full democracy), Freedom House Free, INFORM Risk 1.9/10, US travel advisory Level 1, Canada advisory Level 0, German AA no warning. The country baseline genuinely earns the "Clear" classification.

> **Important:** Day=Night=83.7 is **not** an indication that Alfama is risk-flat across the diurnal cycle. It is a country-baseline rollup applied uniformly to **all 257 cells in the res-5 parent** (most of inner Lisbon). RHYO has not yet computed a cell-resolved night-specific delta for Lisbon. The true Alfama-specific operational risk picture is in §3 (cell-level Eurostat NUTS3 signals) and §8 (qualitative threat list — pickpocketing concentration, slip injury, Tram 28 hazards).

**Surrounding cells (k-ring 2):** **only 3 cells with data** — Alfama sits on the Tagus riverfront, with most of the standard 19-cell ring falling in the river. The 3 land-side cells all show 83.7/83.7 (uniform country fallback).

**Wider 257-cell res-5 parent (most of inner Lisbon):** day=83.7 / night=83.7, crime=0.42, flood=0.10, lighting=0.07, emergency=0.07, building density=0.16, business=0.12, green space=0.09, cellular=0.06, road=0.18 — **uniform across the parent**, confirming country-level fallback.

---

## 2. CELL-LEVEL RISK FACTORS (9-Factor AHP, neighbor-proxy cell `8839336695fffff` — same parent as Alfama)

The target Alfama cell `8839336765fffff` is missing from safety_scores (riverfront edge), so the 9-factor breakdown is read from a representative cell (`8839336695fffff`) inside the same res-5 parent:

| Risk Column | Value | Read |
|---|---|---|
| **crime_risk** | 0.42 | Moderate — Portugal national homicide 0.83/100K is very low; the 0.42 risk reflects high tourist-density concentration of pickpocketing/petty theft, not violent crime |
| **flood_risk** | 0.10 | Low — Tagus tidal range modest; HANZE historical floods = 0.09 |
| **emergency_access_risk** | **0.07** | **Very low** — Portugal physician density 5.85/1000 (top decile), Eurostat NUTS2 unmet medical needs = 0.006 |
| **road_quality_risk** | 0.18 | Low — but **Alfama is the exception**: cobblestone, steep, narrow medieval alleys; Eurostat NUTS3 road victims = 0.27 |
| **lighting_risk** | **0.07** | **Very low** — full European street-lighting infrastructure |
| **building_density_risk** | 0.16 | Low — Alfama specifically has dense low-rise medieval stock; some pre-1755 surviving buildings |
| **cellular_risk** | 0.06 | Very low — MEO/NOS/Vodafone Portugal coverage strong |
| **business_activity_risk** | 0.12 | Low — high tourist commercial density = natural surveillance |
| **green_space_risk** | 0.09 | Low — Castelo de São Jorge gardens, Miradouro de Santa Catarina, Jardim do Tabaco within walking distance |

---

## 3. RAW SIGNALS PRESENT AT TARGET CELL & SAMPLE PARENT-CELL

### Target Alfama cell `8839336765fffff` (8 covariates — sparse due to riverfront position)

| Signal | Value | Source | Date |
|---|---|---|---|
| OSM fire stations (EU) | **1.00 (very close)** | OSM Overpass (RHYO Q30) | 2026-04-10 |
| **Lisbon emergency infra (CML)** | **0.62** — Lisbon City Council ArcGIS feed | Câmara Municipal de Lisboa | 2026-04-10 |
| OSM pharmacies (EU) | **0.011 (top 1%)** | OSM Overpass | 2026-04-10 |
| OSM streetlight density (EU) | 0.0 (cell-level OSM gap on this hex) | OpenStreetMap | 2026-04-07 |
| Street lighting density (legacy OSM) | 0.0 | OSM | 2026-04-07 |
| E-PRTR industrial proximity | 0.06 (low — no major polluters near) | EEA E-PRTR | 2026-04-07 |
| GESLA extreme sea level | 0.02 (low) | GESLA-4 | 2026-04-07 |
| PSMSL sea level trend | 0.0 (Lisbon Tagus subsidence is minimal) | PSMSL | 2026-04-07 |

### Sample parent-cell `8839336695fffff` (15 covariates — fuller picture for adjacent Lisbon cell)

| Signal | Value | Source | Date |
|---|---|---|---|
| **Eurostat NUTS3 crime (recorded)** | **1.00 (max)** — Lisbon NUTS3 has high recording / reporting rate | Eurostat/CRIM | 2026-04-10 |
| Eurostat NUTS3 crime | 0.34 (cell-resolved crime score) | Eurostat/crim_gen_reg | 2026-04-10 |
| **Eurostat NUTS2 physicians** | **0.99 (very high — Lisboa NUTS2 is one of EU's best-staffed)** | Eurostat/HLTH | 2026-04-10 |
| Eurostat NUTS2 hospital beds | 0.52 | Eurostat/HLTH | 2026-04-10 |
| **Eurostat unmet medical needs** | **0.006 (essentially zero)** | Eurostat/HLTH | 2026-04-10 |
| Eurostat NUTS2 GDP per capita | 0.77 (Lisboa is wealthiest Portugal NUTS2) | Eurostat/NAMA | 2026-04-10 |
| Eurostat NUTS2 life expectancy | 0.28 | Eurostat/DEMO | 2026-04-10 |
| Eurostat NUTS2 population density | 0.70 | Eurostat/DEMO | 2026-04-10 |
| Eurostat NUTS2 road victims | 0.32 | Eurostat/TRAN | 2026-04-10 |
| Eurostat NUTS3 road victims | 0.27 | Eurostat/tran_r_acci | 2026-04-11 |
| HANZE historical floods | 0.09 (low) | HANZE v2.1 (Zenodo) | 2026-04-07 |
| E-PRTR industrial proximity | 0.06 | EEA E-PRTR | 2026-04-07 |
| TI-CPI corruption proxy | **0.43 (low — Portugal scores well)** | TI-CPI 2024 | 2026-04-05 |
| CHIRPS precipitation (Feb) | 0.36 | UCSB/CHG | 2026-02 |
| Eurostat physicians (NUTS2) | 0.0 (alternate-key duplicate; ignore) | Eurostat/hlth_rs_physreg | 2026-04-11 |

**Operationally most useful:** the **Lisbon CML emergency-infrastructure feed (0.62)** is a city-government live signal of fire/medical/police facility coverage — Alfama is well-equipped but the 0.62 (vs 1.0 max) reflects Alfama's **medieval narrow streets** that fire engines and ambulances cannot reach quickly.

---

## 4. NEAREST EMERGENCY MEDICAL — Verified hospital proximity

OSM pharmacies (EU dataset) at this cell = **0.011 (top 1% globally)**. Major Lisbon facilities within ~3 km of Alfama:

- **Hospital de São José** (R. de José António Serrano, Mouraria) — public, Centro Hospitalar Universitário de Lisboa Central, **~700 m walking** from Alfama; 24/7 ER
- **Hospital de Santo António dos Capuchos** (Alameda Santo António dos Capuchos) — public, ~1.5 km
- **Hospital de Santa Marta** (R. de Santa Marta) — public cardiology specialty, ~2 km
- **Hospital CUF Tejo** (Av. 24 de Julho) — private flagship, JCI-accredited (CUF group), **~3 km via Praça do Comércio**
- **Hospital da Luz Lisboa** (Av. Lusíada) — private, JCI-accredited, ~7 km
- **Hospital de Santa Maria** (Av. Prof. Egas Moniz) — public CHULN flagship, ~5 km
- **Hospital de Sant'Ana** (Parede) — private, ~25 km west

**Public Portuguese health system (SNS) is universal and treats foreign visitors at the same standard as residents.** EU citizens with EHIC card are covered; non-EU citizens pay (typically modest by US standards). JCI-accredited care (CUF, Luz) is reachable in **15–30 min outside peak**.

*Sources: OSM/Overpass EU pharmacies (2026-04-10), Lisbon CML ArcGIS (2026-04-10), JCI directory (2026-04-08), Eurostat NUTS2 physicians (2026-04-10).*

**Portuguese emergency numbers:**
- **112** — **Unified emergency** (police, fire, ambulance) — EU-standard
- **115** — Saúde 24 (health information line; English-capable nurse triage)
- **PSP (Polícia de Segurança Pública)** — urban police; Esquadra de Turismo (Tourism Squad) at Praça dos Restauradores has English-speaking officers and is the **first stop for foreigner incidents**
- **GNR (Guarda Nacional Republicana)** — rural / national; not Lisbon city
- **Polícia Marítima** — for waterfront / Tagus / harbor incidents

---

## 5. CITY & DISTRICT-LEVEL THREATS (Lisbon / Santa Maria Maior / Alfama)

| Indicator | Value | Source |
|---|---|---|
| **Wikivoyage Portugal safety composite** | **66.4 / 100** (caution band — but PT is misclassified by the keyword extractor; see §10) | RHYO text-extraction pipeline 2026-04 |
| **Airbnb perception index (Lisbon)** | (no Lisbon row in current snapshot — Inside Airbnb covers Lisbon but not in country_indicators) | — |
| **WEF TTDI Safety pillar (Portugal)** | **5.9 / 7.0 — highest in this report set** | WEF 2024 |
| **WEF TTDI Overall** | 4.78 / 7.0 | WEF 2024 |
| **Portugal homicide rate** | **0.83 / 100K (WHO 2021)** — among lowest globally; Lisbon-specific ~1.0/100K | WHO GHO |
| **Portugal UNODC homicide** | 1.2 / 100K | UNODC 2024 |
| **Portugal OWID homicide** | 0.72 / 100K | OWID |
| **Portugal UNODC kidnapping** | 2.92 / 100K (low) | UNODC-CTS |
| **Eurostat NUTS3 (Lisbon) crime score** | 0.34 (cell-level) | Eurostat 2026-04 |

Alfama is **the oldest district of Lisbon** — sole pre-1755-earthquake survival pocket, narrow medieval alleys, steep cobblestone hills, fado houses, miradouros (Santa Luzia, Portas do Sol, Senhora do Monte), Castelo de São Jorge crowning the hill. It sits in the parish of **Santa Maria Maior** (one of the merged parishes of central Lisbon since 2012). Tram 28 (Carris) runs the historic loop through Estrela – Lapa – Baixa – Alfama – Graça and is **the most reliably-pickpocketed transit vehicle in continental Europe** by published consular advisory consensus.

---

## 6. NATIONAL-LEVEL CONTEXT (Portugal — selected indicators)

### Travel advisories (state actor sources)
| Source | Level | Score |
|---|---|---|
| **US State Department** | **Level 1 — Exercise Normal Precautions** (lowest US tier) | 0.10 |
| **US State Dept threat composite** | 0.10 (info — lowest in this report set) | info |
| **UK FCDO** | "1D / 2W / 3C" composite | 0.50 (warning — but lowest in this report set) |
| **German Auswärtiges Amt** | **No travel warning** | 0.0 |
| **Canada (travel.gc.ca)** | **Level 0 / 4** — **safest tier (only PT in this set)** | 0.0 |
| **CDC (US health)** | 6 active health notices | 0.60 |

> *Portugal is rated at the safest tier by every major foreign-ministry advisory in this report set. The CDC's "6 active health notices" reflect generic EU-wide advisories (measles, polio sub-clinical), not Portugal-specific risk.*

### Crime / homicide / violence (national)
- **WHO intentional homicide:** **0.83 / 100K (2021)** — **the lowest of the five countries in this set** (Bangkok TH 4.4, CDMX MX 28.2, Istanbul TR 4.8, Bali ID ~0.6); among the safest 15 countries globally
- **UNODC homicide:** 1.2 / 100K
- **OWID homicide:** 0.72 / 100K
- **OWID conflict deaths 2025:** **0**
- **OWID terrorism deaths 2021:** **0** — Portugal has no recent terrorism incidents
- **UNODC kidnapping:** 2.92 / 100K (low)
- **Mass Mobilization protest events:** 33 (19 recent, 1 violent state response — by Western European norms, very calm)

### Governance & rule of law
- **Freedom House Status:** **Free (Status=1, top tier)** — Civil Liberties=1/7 (info), Political Rights=1/7 (info)
- **V-Dem Liberal Democracy:** 0.758 (info — top tier)
- **V-Dem Electoral Democracy:** 0.844 (info)
- **V-Dem Political Corruption:** 0.140 (info — very low)
- **Polity5:** **+10** (full democracy; 1976 transition stable)
- **WJP Order and Security:** 0.78 (info — high)
- **WJP Constraints on Government:** 0.75 (info — high)
- **WJP Fundamental Rights:** 0.75 (info)
- **WJP Criminal Justice:** 0.57 (caution — middle)
- **TI Corruption Perceptions:** 62/100 (caution — best in this set; OECD-average for TI)
- **WB Control of Corruption:** +0.82 (percentile 65%, caution band — middle for OECD)
- **WB Rule of Law:** +1.07 (info — strong)
- **WB Voice & Accountability:** +1.27 (info — percentile 79%, strong)
- **WB Political Stability:** +0.54 (caution but stable)
- **PTS Political Terror:** 2.0/5 (info — best in this set)
- **Cline Center coups:** 9 historical, **0 post-2000** (last attempted coup 1974 — the Carnation Revolution, which **succeeded peacefully** and ended Estado Novo dictatorship)
- **INFORM Risk Index:** **1.9 / 10 (info — lowest in this report set)**
- **INFORM Hazard Exposure:** 1.9
- **INFORM Coping Capacity:** 1.7
- **INFORM Vulnerability:** 2.2
- **Global Peace Index:** **1.37 (Portugal ranks ~7/163, top tier)**

### Public health (PT is OECD-strong)
- **Life expectancy:** **82.4 yrs (WB) — highest in this report set**
- **WB physicians per 1000:** **5.85 (top decile globally)**
- **WHO PM2.5 annual:** 7.3 µg/m³ (info — **under the WHO 10 µg/m³ guideline**, only PT in this set)
- **WB current PM2.5:** 8.5 µg/m³ (info)
- **Adult HIV prevalence:** 0.5% (caution; concentrated in Lisbon and Porto)
- **WHO DPT3 immunization:** 99% (excellent)
- **WHO TB incidence:** 20/100K (low)
- **Malaria:** **0** (eliminated)
- **WHO UHC service coverage:** 83/100
- **WB inflation (2024):** 2.4% (low — euro)
- **WB unemployment:** 5.9% (low)
- **WB urban population:** 61.3%
- **WHO alcohol per capita:** **11.2 L (warning — high; wine country)**
- **JMP "basic" sanitation 5.7% / "basic" water 4.1%** are misleading: **safely-managed sanitation 93.9% / safely-managed water 95.2%** — PT residents are overwhelmingly on safely-managed services, the "basic-only" tier is almost empty by definition

### Hazards
- **EM-DAT natural disasters:** 39 events with 8,021 deaths — heavily skewed by:
  - **2017 Pedrógão Grande wildfires:** 66 dead (June), 50+ dead (October)
  - 2003 wildfires
  - Historic 1755 Lisbon earthquake (~30,000 dead — civilization-altering event for the city)
- **WRI Aqueduct riverine flood:** 0.73 / 5 (low)
- **WRI Aqueduct water stress:** 3.26 / 5 (moderate)
- **WRI Aqueduct drought:** 2.92 / 5
- **WRI World Risk Index:** (PT not in current snapshot)
- **GBIF venomous species:** Mediterranean vipers in rural PT, near-zero in Lisbon
- **GDACS active events:** 0
- **Earthquake hazard:** **The 1755 Lisbon earthquake is the historic anchor** — M~8.5 offshore Atlantic event triggered tsunami that destroyed downtown. **Recurrence interval estimated 200–500 years**; instrumental seismicity since 1755 has been modest. Portugal does have an active fault system (Lower Tagus Fault, Atlantic margin) but **decadal-aggregated risk is much lower than Istanbul or CDMX**. **Tsunami risk for the Tagus estuary is real but rare.**

### Social & rights
- **Equaldex equality index:** **0.77 (high — best in this report set)**
- **Equaldex legal index:** 0.94 (very high — same-sex marriage 2010, gender identity 2018, conversion-therapy ban 2024)
- **Equaldex public opinion:** 0.60
- **WBL women's safety legal score:** 31.25 (warning) — anomalously low for PT given strong DV laws and EU framework; treat as methodology-limited
- **Gender Inequality Index:** (not in current snapshot, but PT scores ~0.06 in UNDP HDR — among best in EU)
- **TIP Report tier:** Tier 2 (caution) — Portugal is destination + transit for trafficking from Brazil, Eastern Europe, West Africa
- **AMAR at-risk minorities:** 0 groups (no formal at-risk minority designation)
- **Discrimination perception (Eurobarometer 2023):** 0.61 (caution)

### Surveillance & legal-strict regime (relevant for tourists)
- **Comparitech CCTV density:** (not in PT snapshot; Lisbon urban CCTV is moderate)
- **Comparitech censorship:** 10/100 (warning — methodology; PT has no meaningful censorship)
- **Comparitech SIM registration:** **mandatory** (EU-wide eIDAS framework)
- **Comparitech biometric:** 8/25 (warning)
- **Wiki drug legality:** **0.15 (info — Portugal famously decriminalized all drugs in 2001)** — possession of personal-use quantities is administrative, not criminal; treatment-oriented model. Cannabis still technically illegal but personal possession ≤25g handled by Comissões para a Dissuasão da Toxicodependência (CDT). **Trafficking remains criminal.**
- **Death penalty:** **abolished 1867** (Portugal was the first European country to abolish for ordinary crimes; second in Europe overall)
- **Press freedom:** RSF rank ~10/180 (top tier)

### Road safety
- **WHO road traffic deaths:** 7.2 / 100K (info) — among safer EU members but **above Western European median** (Sweden 2, UK 2.5, Netherlands 3, Germany 3.5)
- **WB road mortality:** 8.2 / 100K
- **Driving side:** right (continental EU)
- **Lisbon-specific:** Alfama's narrow cobblestone streets are **NOT cars-and-pedestrians-can-coexist territory** — Tram 28 dominates, scooters and tuk-tuks weave through, foot traffic shares lanes. Slip and fall on wet cobblestones is the most common Alfama injury vector by ER admission.

---

## 7. ENVIRONMENTAL & EPIDEMIOLOGICAL RISKS — Lisbon-specific

### Slips, trips, falls (the dominant Alfama-specific physical risk)
- **Calçada portuguesa** (Portuguese pavement) — small white-and-black limestone-and-basalt cubes laid in patterns — is **slippery when wet** (Lisbon humidity) and **slippery when polished** (centuries of foot traffic on Alfama steps). Lisbon's tourism trauma admissions are dominated by ankle/wrist/hip injuries from cobblestone falls.
- Alfama-specific: stairs without railings, irregular step heights, Tram 28 tracks at street level
- Mitigation: rubber-soled shoes (NOT smooth-leather); use trekking-pole if mobility-limited; descend rather than ascend in rain

### Heat / fire
- Mediterranean climate: hot dry summers (28–35 °C, peaks 40+ °C in heatwaves), mild wet winters (10–15 °C)
- **Wildfire season (May–October)** affects rural PT (2017 Pedrógão Grande, 2003 events) — does NOT directly threaten Alfama, but **smoke plumes do reach Lisbon** during major events; PM2.5 spikes to 100+ µg/m³ for days
- Mitigation: monitor Portuguese Civil Protection (ANEPC) alerts; N95 during smoke episodes

### Air quality
- Lisbon annual mean PM2.5: ~8–12 µg/m³ baseline (WHO national 7.3; WB 8.5 — among best in this set)
- **No regular pollution alerts** outside wildfire smoke episodes
- Atlantic ventilation keeps Lisbon clean

### Water & food
- **Tap water in Lisbon is potable and tested to EU standards** — drink it freely
- **Travelers' diarrhea:** baseline ~5–10% in first week (lowest in this report set)
- **Hep A vaccine recommended** for any international travel, otherwise minimal vaccine prep
- Street food (bifana, sardines in season, pastéis de nata) is broadly safe

### Vector-borne disease
- **Dengue / Chikungunya / Zika:** absent from continental PT; Madeira had a 2012 dengue outbreak (autochthonous *Aedes aegypti*) which sparked surveillance — Lisbon has no resident *Aedes*
- **Malaria:** **eliminated**
- **West Nile virus:** sporadic horse / human cases in Algarve / Alentejo (rural southern PT) — not Lisbon
- **Rabies:** PT is rabies-free

### Earthquakes / tsunami
- **1755 Lisbon earthquake** (M~8.5, ~30,000 dead, tsunami inundation of Tagus estuary) is the historic anchor — recurrence interval ~200–500 years
- Modern building stock is moderately well-prepared; **Alfama itself is the survival district from 1755** — many of the standing structures are 16th–17th century stone construction that withstood the event
- Tsunami warning: Lisbon civil protection has tsunami evacuation routes; Alfama is at moderate elevation (Castelo de São Jorge ~110 m) and is **safer than the Baixa** (which sits at sea level on reclaimed marshland)

### Sun exposure
- Latitude 38.7° N + summer UV index 8–10 → real sunburn risk; Alfama miradouros have minimal shade

### Pickpocketing-adjacent injury
- Bag-snatch with mild violence has been documented in Alfama during summer peak (June–September) — not predominant pattern but worth noting

---

## 8. ANTHROPOGENIC / CRIME-PROXIMATE RISKS

### What does NOT meaningfully apply to Lisbon / Alfama:
- **Terrorism (current and historic)** — Portugal has had **zero terrorism deaths in 2021** (OWID), and no significant attack since the late-1980s ETA-spillover era. Foreign-ministry advisories acknowledge this.
- **Active conflict zone** — flag = false; PT is at peace, NATO member, EU member
- **Kidnap-for-ransom** — effectively zero
- **Civil unrest disrupting tourist quarter** — 33 protest events in current snapshot is by EU norms very calm; Alfama specifically is not on protest routes (which cluster Praça do Comércio, Praça da Figueira, Saldanha)
- **Cartel / organized crime targeting tourists** — Portugal's drug trade is significant (transit) but does NOT manifest as tourist-targeted violence
- **Informal settlement** — flag = false
- **Authoritarian-state risk** — Portugal Polity5 +10, Voice & Accountability +1.27 — fully democratic, low risk for political-speech detention

### What DOES apply (the operative threat list for Alfama):

| Risk | Notes |
|---|---|
| **Pickpocketing on Tram 28** | **THE single highest-frequency adverse event** for tourists in Lisbon. Tram 28 (Estrela – Martim Moniz loop) passes through Alfama with packed standing-room-only summer crowds. Operating model: 2–3 person crews, one creates pressure/distraction, the other extracts wallet/phone from outer pockets, third blocks pursuit. **Wear bags cross-body inside chest layer; nothing in back/outer pockets; phone on lanyard or zipped pocket.** |
| **Pickpocketing at miradouros** | Santa Luzia, Portas do Sol, Senhora do Monte, Graça — distracted-tourist pattern at viewpoints |
| **Pickpocketing at Praça do Comércio / Baixa metro** | Adjacent to Alfama — same crew demographics |
| **Slip/fall on calçada portuguesa** | See §7 — by ER admissions, **the most likely way a tourist is hospitalized in Lisbon** |
| **Street-drug "sales" to tourists (fake hashish, fake cocaine)** | Long-established Lisbon scam — dealers in Bairro Alto, Cais do Sodré, occasionally Alfama edges, sell oregano-baking-soda mix as cannabis or aspirin as cocaine. Walking away is fine; they rarely escalate. **Decriminalization does NOT make it legal to buy from a dealer**, just unlikely to result in criminal prosecution if caught with personal-use quantities. |
| **Tuk-tuk / Tram 28 fare gouging** | Alfama tuk-tuk operators sometimes overcharge tourists; agree price before mounting |
| **Bag-snatch on motorbike (rare but documented)** | Less common than CDMX or Istanbul but recorded in summer peak; carry bag away from street side |
| **Beach drug-dealer extortion (Cascais / Costa da Caparica)** | Not Alfama-specific; relevant if itinerary extends to Atlantic beaches |
| **Restaurant menu-swap / hidden surcharge** | Couvert (bread, olives, cheese delivered uninvited to table) is a documented bill-padding pattern — say "não, obrigado/a" if you don't want it; you are not obligated to pay for unrequested items by Portuguese consumer law (DL 10/2015). |
| **ATM card-skimming** | Lower frequency than CDMX/Istanbul but documented; use bank-branch ATMs (Multibanco / SIBS / Caixa Geral de Depósitos) |
| **Tram 28 line operational accidents** | Tourists struck by trams crossing tracks (silent approach from behind; visual focus on Alfama vista). Multiple injuries annually. **Look both ways every track-cross.** |
| **Hill / stair injury** | See §7. Especially descending in rain. |
| **Drink-spiking** | Lower than other cities in this set but documented (Cais do Sodré "Pink Street", Bairro Alto bar circuit) |
| **Romance / dating-app extortion** | Rare; Portugal scores well on these measures |
| **Sex-tourism solicitation** | Cais do Sodré and Bairro Alto have visible sex work presence; Alfama proper does not |
| **Pre-1755 building condition** | Some unreinforced masonry stock in Alfama; 1755 earthquake left this district relatively intact, but 270-year-old structures should be inspected for accommodation. Generally low risk because PT's seismic recurrence is much longer than TR's. |

---

## 9. TARGETED THREAT PROFILE — for a Western solo tourist in Alfama

The risk delta between this individual and a generic Lisboeta is concentrated in three categories:

1. **Pickpocketing on Tram 28 / at miradouros** — by frequency, this is the dominant tourist-targeted adverse event in Lisbon and Alfama is at the geographic concentration of the route. Mitigation: cross-body bag inside layer, no outer pockets, phone secured, distraction-pattern awareness (someone bumps you / asks for directions / drops something).
2. **Calçada-portuguesa slip injury** — by ER admission, this is the most likely way you end up in a Lisbon hospital. Mitigation: rubber-sole shoes; descend rather than ascend stairs in rain; stay on dry side of street.
3. **Tram 28 / tuk-tuk traffic discipline** — Tram 28 is silent from behind; Alfama tuk-tuks weave aggressively. Mitigation: track-crossing protocol; don't dawdle on tracks for photos.

**There is no credible terrorism, kidnap-for-ransom, political-violence, or organized-crime targeting risk to a tourist in Alfama under normal circumstances.** Portugal is materially safer than Bangkok, CDMX, Istanbul, or Bali on every measured violence axis. The realistic life-threatening incidents are, in descending order:

1. Cobblestone slip → head/hip injury (esp. for older visitors)
2. Tram 28 collision (less common but historically fatal)
3. Cardiac event aggravated by Alfama's hill profile + heat (esp. for older visitors in summer)
4. Drowning at Cascais / Costa da Caparica beaches (separate-itinerary risk; Portugal Atlantic surf is genuinely dangerous)
5. Pickpocketing escalation to violence (extremely rare in PT)
6. Tsunami (decade-aggregated, very high consequence — 1755 recurrence)
7. Wildfire smoke during Pedrógão-class event (rural fires reach Lisbon as PM2.5 plumes)

---

## 10. RHYO DATA QUALITY DISCLOSURES

- **Target Alfama cell `8839336765fffff` is missing from `intelligence.safety_scores`** — the cell is present in `covariate_layers` (8 covariates) but no scoring row exists. The most likely cause is the cell sits at the Tagus riverfront edge and was excluded by a land-coverage filter. **All five Alfama-area sub-coordinates tested (Castelo de São Jorge, Miradouro Santa Luzia, Baixa adjacency, Sé) resolve to either this same `8839336765fffff` cell or `88393362b3fffff`, both of which are missing.** Surrounding cells in the same res-5 parent ARE in safety_scores.
- **Proxy cell `8839336695fffff`** (same res-5 parent, ~1 km away) is used for the 9-factor breakdown and Eurostat NUTS3 signals.
- **All 257 cells in the res-5 parent (most of inner Lisbon) carry uniform 83.7/83.7 day/night** — this is country-baseline fallback. **0 of 115,077 PT cells are recorded at `municipal` fallback level** in the current snapshot, vs Mexico where municipal fallback is the norm. The Portugal scoring layer has not yet been promoted to municipal-fallback for any city.
- **The 83.7 "Clear" rating accurately reflects Portugal's structural safety profile** (homicide 0.83/100K, GPI 1.37, Polity5 +10, US Level 1, Canada Level 0) — but does NOT reflect Alfama-specific tourist-pickpocketing concentration. The headline composite is correct at the country-aggregate level and conservative-but-uninformative at the Alfama-block level.
- **Wikivoyage safety score 66.4** is anomalously low for Portugal given the actual safety baseline; the keyword-extraction methodology assigns "caution" because Wikivoyage's PT article documents pickpocketing and slips. The composite homicide and advisory data dominate the true picture.
- **Day=Night=83.7** is NOT cell-resolved diurnal-uniform truth — it is a known limitation: Q26 women_safety_score_night and night-specific variants pending (CLAUDE.md §36).
- **Eurostat NUTS3 crime score = 0.34** at the proxy cell is the cell-level signal for Lisbon-area crime rate.
- **Eurostat NUTS3 crime recorded = 1.00** indicates Lisbon NUTS3 has the *highest* recording/reporting density in the Eurostat dataset — this is a **good sign** (under-reporting is a key safety-data confound) and should NOT be misread as "highest crime."
- **The Lisbon CML (Câmara Municipal) emergency-infrastructure live feed** at 0.62 is one of the strongest municipal-government signals in this report set.
- **`women_safety_score_night` is null** — Q26 SQL function pending.
- **Database state:** Hetzner PG cluster online; Portugal coverage 115,077 res-8 cells; ~395 country indicators on file. Score recompute timestamp: most recent.
- **Sources cited inline.** Verifiable via: WHO GHO, World Bank WDI/WGI, UNODC, EM-DAT/CRED, Eurostat (CRIM, HLTH, NAMA, DEMO, TRAN), OSM/Overpass (incl. Q30 EU layers), Lisbon CML ArcGIS, JCI directory, HANZE v2.1, EEA E-PRTR, GESLA-4, PSMSL, US State Dept, UK FCDO, German AA, Canada travel.gc.ca, CDC, INFORM/HDX, NTI GHSI, WEF TTDI, Wikivoyage, Inside Airbnb, Comparitech, Equaldex, WBL 2026, Freedom House, V-Dem, Polity5, Cline Center, Fund for Peace, Mass Mobilization Project, Wiki/UNODC drug-legality dataset, Global Peace Index 2024, OWID.

---

## ONE-LINE BOTTOM LINE
**Alfama sits inside Portugal's "Clear" national-safety baseline — by every aggregate violence and governance measure, the safest of the five cities in this report set — where the realistic threats to a Western solo tourist's life are, in order: (1) calçada-portuguesa slip-and-fall (esp. in rain or descending), (2) Tram 28 collision crossing tracks, (3) cardiac event aggravated by Alfama hill profile + summer heat, (4) Cascais/Caparica drowning if itinerary extends to beach, (5) pickpocketing escalation in extremely rare cases — NOT terrorism, NOT kidnapping, NOT violent street crime; pickpocketing on Tram 28 is the most-likely-to-happen incident; call 112 or visit PSP Esquadra de Turismo at Praça dos Restauradores for foreigner incidents.**
