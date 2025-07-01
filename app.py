import pandas as pd
import streamlit as st
import re
from datetime import datetime
import os

# Konfigurujeme pandas pro lepší práci s velkými soubory
pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', None)

# Funkce pro normalizaci textu při porovnávání
def normalize_text(text):
    if not isinstance(text, str):
        text = str(text)
    # Odstranění nadbytečných mezer, převod na malá písmena
    return re.sub(r'\s+', '', text.lower())

# NOVÁ FUNKCE: Normalizace OBICIS kódů
def normalize_obicis(obicis_code):
    """Normalizuje OBICIS kód odstraněním úvodních nul a mezer"""
    if pd.isna(obicis_code):
        return ""
    
    # Převedeme na string a odstraníme mezery
    code_str = str(obicis_code).strip()
    
    # Odstraníme úvodní nuly
    code_normalized = code_str.lstrip('0')
    
    # Pokud je kód prázdný (byly tam jen nuly), vrátíme "0"
    if not code_normalized:
        code_normalized = "0"
    
    return code_normalized

# Načtení defaultních souborů z kořenového adresáře
@st.cache_data(max_entries=3, ttl=3600)  # Zvýšený cache pro větší soubory
def nacti_defaultni_soubory():
    try:
        vzor = pd.read_excel('vzor.xlsx')
        vazby_znacek = pd.read_excel('vazby_znacek.xlsx', dtype={'A': str})
        return vzor, vazby_znacek
    except Exception as e:
        st.error(f"Chyba při načítání defaultních souborů: {e}")
        return None, None

# Optimalizovaná funkce pro načtení velkých Excel souborů
@st.cache_data(max_entries=10, ttl=3600)
def nacti_velky_excel(file_data, file_name):
    """Načte Excel soubor s optimalizací pro velké soubory"""
    try:
        # Pokusíme se načíst soubor po částech, pokud je velmi velký
        df = pd.read_excel(
            file_data,
            engine='openpyxl',  # Explicitně specifikujeme engine
            dtype=str,  # Načteme vše jako string, abychom předešli problémům s datovými typy
            na_filter=False  # Nezaměňujeme prázdné buňky za NaN
        )
        
        # Konvertujeme zpět na vhodné datové typy tam, kde je to potřeba
        for col in df.columns:
            if df[col].dtype == 'object':
                # Pokusíme se převést číselné sloupce
                try:
                    # Testujeme, jestli je možné převést na číslo
                    pd.to_numeric(df[col], errors='raise')
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                except (ValueError, TypeError):
                    # Pokud ne, necháme jako string
                    pass
        
        st.success(f"Úspěšně načten soubor {file_name}: {len(df)} řádků, {len(df.columns)} sloupců")
        return df
        
    except Exception as e:
        st.error(f"Chyba při načítání souboru {file_name}: {e}")
        return None

# Hlavní funkce pro zpracování s volitelnou plnou diagnostikou
def zpracuj_soubory(vazby_produktu, vazby_akci, zlm, full_diagnostics=False):
    vzor, vazby_znacek = nacti_defaultni_soubory()
    if vzor is None or vazby_znacek is None:
        return None

    vysledek = pd.DataFrame(columns=vzor.columns)
    
    # Příprava vyhledávacích slovníků (indexů)
    st.write("Vytvářím indexy pro rychlejší zpracování...")
    
    normalized_vazby_znacek = {normalize_text(row.iloc[2]): row.iloc[0] for _, row in vazby_znacek.iterrows()}
    
    vazby_produktu_dict = {}
    for _, row in vazby_produktu.iterrows():
        key_raw, value_raw = row.iloc[2], row.iloc[0]
        if pd.isna(key_raw) or pd.isna(value_raw):
            continue
        key = str(key_raw).strip()
        vazby_produktu_dict.setdefault(key, []).append(str(value_raw).strip())
    
    zlm_dict = {}
    duplicity_count = 0
    for _, row in zlm.iterrows():
        key_raw = row.iloc[2]
        if pd.isna(key_raw):
            continue
        
        key_original = str(key_raw).strip()
        key_normalized = normalize_obicis(key_original)
        
        if key_normalized in zlm_dict:
            duplicity_count += 1
            continue
            
        zlm_dict[key_normalized] = {
            'kod_zbozi': str(row.iloc[1]),
            'klubova_info': str(row.iloc[12]) if len(row) > 12 else ""
        }
    
    if duplicity_count > 0:
        st.warning(f"Nalezeno a ignorováno {duplicity_count} duplicitních OBICIS kódů v ZLM souboru (použil se první výskyt).")
    
    st.write(f"Indexy vytvořeny. Vazby produktu: {len(vazby_produktu_dict)} klíčů, ZLM: {len(zlm_dict)} klíčů.")
    
    progress_bar = st.progress(0)
    total_rows = len(vazby_akci)
    
    for index, radek_akce in vazby_akci.iterrows():
        progress_bar.progress((index + 1) / total_rows)
        
        id_dlazdice_raw = radek_akce.iloc[1]
        if pd.isna(id_dlazdice_raw):
            continue
        id_dlazdice = str(id_dlazdice_raw).strip()
        
        obicis_list = vazby_produktu_dict.get(id_dlazdice, [])
        kody_zbozi = []
        klubova_akce = 0
        
        # LOGIKA PRO KLUBovou akci
        ken_sloupec_h = str(radek_akce.iloc[7]).strip() if len(radek_akce) > 7 else ""
        if ken_sloupec_h == "1":
            klubova_akce = 1
        
        zlm_klub_info_values = []
        zlm_condition_met = False
        for obicis in obicis_list:
            obicis_normalized = normalize_obicis(obicis)
            zlm_data = zlm_dict.get(obicis_normalized)
            
            if zlm_data:
                raw_kod = zlm_data['kod_zbozi']
                kody_zbozi.append(str(raw_kod).split('.')[0].zfill(18))
                
                klub_info = zlm_data['klubova_info'].strip()
                zlm_klub_info_values.append(f"'{klub_info}' (z OBICIS {obicis_normalized})")
                if klub_info.upper().startswith("MK"):
                    klubova_akce = 1
                    zlm_condition_met = True
        
        slug = id_dlazdice.lower()
        if slug.startswith("sk"):
            klubova_akce = 1

        # Určení hodnoty pro sloupec D
        if slug.startswith("te"): column_d_value = "leaflet"
        elif slug.startswith("ma"): column_d_value = "magazine"
        elif slug.startswith("dz"): column_d_value = "longTermDiscount"
        elif slug.startswith("kp"): column_d_value = "coupons"
        else: column_d_value = "leaflet"

        # ## PLNÁ DIAGNOSTIKA (POKUD JE ZAPNUTÁ) ##
        if full_diagnostics:
            st.markdown("---")
            st.write(f"**DIAGNOSTICKÝ PŘEHLED pro řádek {index+1} (ID dlaždice: `{id_dlazdice}`)**")
            
            # Podmínka 1
            st.write(f"- `Podmínka 1 (KEN Sloupec H)`: Nalezená hodnota je **'{ken_sloupec_h}'**. Podmínka (`== '1'`) je **{'splněna' if ken_sloupec_h == '1' else 'nesplněna'}**.")
            
            # Podmínka 2
            if not zlm_klub_info_values:
                msg = "Pro OBICIS kódy nebyly v ZLM nalezeny žádné relevantní záznamy."
            else:
                msg = f"Nalezené hodnoty v ZLM sloupci M: {', '.join(zlm_klub_info_values)}."
            st.write(f"- `Podmínka 2 (ZLM Sloupec M)`: {msg} Podmínka (začíná na 'MK') je **{'splněna' if zlm_condition_met else 'nesplněna'}**.")

            # Podmínka 3
            st.write(f"- `Podmínka 3 (ID dlaždice)`: Hodnota je **'{slug}'**. Podmínka (`začíná na 'sk'`) je **{'splněna' if slug.startswith('sk') else 'nesplněna'}**.")
            
            st.success(f"-> **FINÁLNÍ HODNOTA pro Sloupec B bude: `{klubova_akce}`**")
        
        # Sestavení řádku
        nazev_znacky = radek_akce.iloc[6]
        id_znacky = normalized_vazby_znacek.get(normalize_text(nazev_znacky), "")
        
        datum_hodnota = radek_akce.iloc[4]
        try:
            datum_string = pd.to_datetime(datum_hodnota).strftime('%Y-%m-%d') if not pd.isna(datum_hodnota) else ""
        except (ValueError, TypeError):
            datum_string = str(datum_hodnota)
        
        novy_radek = {
            vzor.columns[0]: 1,
            vzor.columns[1]: klubova_akce,
            vzor.columns[2]: radek_akce.iloc[5],
            vzor.columns[3]: column_d_value,
            vzor.columns[4]: radek_akce.iloc[16] if len(radek_akce) > 16 else "",
            vzor.columns[5]: slug,
            vzor.columns[6]: radek_akce.iloc[2],
            vzor.columns[7]: f"{datum_string} 23:59" if datum_string else "",
            vzor.columns[8]: f"{id_dlazdice.upper()}.jpg",
            vzor.columns[9]: id_znacky,
            vzor.columns[10]: ','.join(kody_zbozi)
        }
        vysledek = pd.concat([vysledek, pd.DataFrame([novy_radek])], ignore_index=True)
    
    progress_bar.progress(1.0)
    st.success("Zpracování dokončeno!")
    
    return vysledek


# Streamlit UI s konfigurací pro větší soubory
st.set_page_config(
    page_title="Generátor marketingových akcí",
    page_icon="📊",
    layout="wide"
)

st.title("Generátor marketingových akcí - Upravená verze s novou logikou klubové akce")
st.write("Nahrajte 3 požadované soubory ve formátu XLSX (podporuje až desítky tisíc řádků):")

# Použití obecného typu souboru místo specifikace přípony
vazby_produktu_file = st.file_uploader("1. Soubor VAZBY produktu", type="xlsx", help="Excel soubor s vazbami produktů")
vazby_akci_file = st.file_uploader("2. Soubor KEN (vazby akcí)", type="xlsx", help="Excel soubor s vazbami akcí")
zlm_file = st.file_uploader("3. Soubor ZLM", type="xlsx", help="Excel soubor ZLM (může obsahovat tisíce řádků)")

st.markdown("---")
st.warning("⚠️ Zapnutí plné diagnostiky může výrazně zpomalit zpracování u velkých souborů a zahltit obrazovku výpisy.")
full_diagnostics_checkbox = st.checkbox("Zobrazit detailní diagnostiku pro každý řádek")

if st.button("Spustit generování s upravenou logikou klubové akce"):
    if all([vazby_produktu_file, vazby_akci_file, zlm_file]):
        try:
            with st.spinner('Načítám a zpracovávám data...'):
                vazby_produktu = nacti_velky_excel(vazby_produktu_file, "VAZBY produktu")
                vazby_akci = nacti_velky_excel(vazby_akci_file, "KEN (vazby akcí)")
                zlm = nacti_velky_excel(zlm_file, "ZLM")
                
                if vazby_produktu is None or vazby_akci is None or zlm is None:
                    st.error("Nepodařilo se načíst všechny soubory.")
                    st.stop()
                
                vysledek = zpracuj_soubory(vazby_produktu, vazby_akci, zlm, full_diagnostics_checkbox)
                
                if vysledek is not None:
                    timestamp = datetime.now().strftime('%d.%m.%Y %H:%M')
                    filename_timestamp = datetime.now().strftime('%Y%m%d_%H%M')
                    
                    csv = vysledek.to_csv(index=False, sep=';', encoding='utf-8-sig')
                    st.success(f"Generování úspěšně dokončeno! (Datum a čas: {timestamp})")
                    st.download_button(
                        label="Stáhnout výsledný soubor",
                        data=csv,
                        file_name=f"vysledek_{filename_timestamp}.csv",
                        mime="text/csv"
                    )
                    
                    if st.checkbox("Zobrazit výslednou tabulku"):
                        st.dataframe(vysledek)
                        
                    st.write("**Statistiky zpracování:**")
                    st.write(f"- Zpracováno řádků: {len(vysledek)}")
                    st.write(f"- Řádky s vyplněnými kódy zboží: {len(vysledek[vysledek.iloc[:, 10] != ''])}")
                    st.write(f"- Řádky bez kódů zboží: {len(vysledek[vysledek.iloc[:, 10] == ''])}")
                    st.write(f"- Řádky s klubovou akcí (sloupec B = 1): {len(vysledek[vysledek.iloc[:, 1] == 1])}")
                
        except Exception as e:
            st.error(f"Došlo k chybě: {str(e)}")
            import traceback
            st.error(f"Detaily chyby: {traceback.format_exc()}")
    else:
        st.warning("Prosím, nahrajte všechny požadované soubory!")

# Původní expander bloky
with st.expander("🔧 Informace o nové logice klubové akce"):
    st.write("""
    **Nová logika pro sloupec B (klubová akce):**
    
    **Sloupec B ve výsledku = 1**, pokud platí JAKÁKOLI z těchto podmínek:
    
    1. **Sloupec H z KEN souboru obsahuje "1"**
        - Nová podmínka pro přímé označení klubové akce v KEN souboru
    
    2. **ZLM obsahuje "MK" v sloupci M (index 12)**
        - Původní logika na základě klubové informace v ZLM
    
    3. **ID dlaždice začíná "sk"**
        - Původní logika na základě prefixu ID
    
    **Provázání dat:**
    - Sloupec B z KEN → Sloupec F výsledku (identifikace)
    - Sloupec H z KEN → Logika pro sloupec B výsledku (klubová akce)
    
    **Diagnostika:**
    - Zobrazuje se, která podmínka způsobila nastavení klubové akce
    - Přidaná statistika počtu řádků s klubovou akcí
    """)

with st.expander("🔧 Informace o opravě OBICIS normalizace"):
    st.write("""
    **Oprava problému s OBICIS kódy:**
    
    **Problém**: OBICIS kódy se v různých souborech liší formátem úvodních nul:
    - V souboru VAZBY: `32001256` (bez úvodních nul)
    - V souboru ZLM: `0032001256` (s úvodními nulami)
    
    **Řešení**:
    1. **Funkce `normalize_obicis()`**: Odstraňuje úvodní nuly z OBICIS kódů
    2. **Normalizace při indexování**: Všechny OBICIS kódy v ZLM jsou normalizovány při vytváření indexu
    3. **Normalizace při vyhledávání**: OBICIS kódy z VAZBY jsou také normalizovány před vyhledáváním
    4. **Zachování originálů**: Pro diagnostiku se uchovávají i originální formáty
    
    **Výsledek**: 
    - `32001256` i `0032001256` se budou považovat za stejný kód
    - Zvýší se úspěšnost párování OBICIS kódů
    - Diagnostika ukáže jak originální, tak normalizované hodnoty
    """)
