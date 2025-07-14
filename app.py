import pandas as pd
import streamlit as st
import re
from datetime import datetime, timedelta
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
    
    # Vytvoření slovníku vazeb produktů - klíčem je ID dlaždice (sloupec C), hodnotou jsou SAPID kódy (sloupec A)
    vazby_produktu_dict = {}
    for _, row in vazby_produktu.iterrows():
        id_dlazdice = row.iloc[2]  # sloupec C - ID dlaždice
        sapid_kod = row.iloc[0]    # sloupec A - SAPID kód
        
        if pd.isna(id_dlazdice) or pd.isna(sapid_kod):
            continue
            
        key = str(id_dlazdice).strip()
        sapid_value = str(sapid_kod).strip()
        
        vazby_produktu_dict.setdefault(key, []).append(sapid_value)
    
    # Vytvoření slovníku ZLM - klíčem je SAPID kód (sloupec A), hodnotou jsou data
    zlm_dict = {}
    duplicity_count = 0
    for _, row in zlm.iterrows():
        sapid_kod = row.iloc[0]  # sloupec A - SAPID kód
        
        if pd.isna(sapid_kod):
            continue
        
        sapid_key = str(sapid_kod).strip()
        
        if sapid_key in zlm_dict:
            duplicity_count += 1
            continue
            
        zlm_dict[sapid_key] = {
            'kod_zbozi': str(row.iloc[1]),  # sloupec B - kód zboží
            'klubova_info': str(row.iloc[12]) if len(row) > 12 else ""  # sloupec M - klubová info
        }
    
    if duplicity_count > 0:
        st.warning(f"Nalezeno a ignorováno {duplicity_count} duplicitních SAPID kódů v ZLM souboru (použil se první výskyt).")
    
    st.write(f"Indexy vytvořeny. Vazby produktu: {len(vazby_produktu_dict)} klíčů, ZLM: {len(zlm_dict)} klíčů.")
    
    progress_bar = st.progress(0)
    total_rows = len(vazby_akci)
    
    for index, radek_akce in vazby_akci.iterrows():
        progress_bar.progress((index + 1) / total_rows)
        
        id_dlazdice_raw = radek_akce.iloc[1]
        if pd.isna(id_dlazdice_raw):
            continue
        id_dlazdice = str(id_dlazdice_raw).strip()
        
        # Získání SAPID kódů pro dané ID dlaždice
        sapid_list = vazby_produktu_dict.get(id_dlazdice, [])
        kody_zbozi = []
        klubova_akce = 0
        
        # ### LOGIKA PRO KLUBOVOU AKCI ###
        # LOGIKA PRO KLUBovou akci - Krok 1: Kontrola sloupce H z KEN
        ken_sloupec_h = str(radek_akce.iloc[7]).strip() if len(radek_akce) > 7 else ""
        is_ken_h_one = False
        try:
            # Pokusíme se hodnotu převést na číslo a porovnat s 1
            if int(float(ken_sloupec_h)) == 1:
                is_ken_h_one = True
        except (ValueError, TypeError):
            # Pokud převod selže (text, prázdná buňka), podmínka není splněna
            is_ken_h_one = False

        if is_ken_h_one:
            klubova_akce = 1
        
        # LOGIKA PRO KLUBovou akci - Krok 2: Kontrola ZLM na základě SAPID kódů
        zlm_klub_info_values = []
        zlm_condition_met = False
        for sapid in sapid_list:
            zlm_data = zlm_dict.get(sapid)
            
            if zlm_data:
                raw_kod = zlm_data['kod_zbozi']
                kody_zbozi.append(str(raw_kod).split('.')[0].zfill(18))
                
                klub_info = zlm_data['klubova_info'].strip()
                zlm_klub_info_values.append(f"'{klub_info}' (z SAPID {sapid})")
                if klub_info.upper().startswith("MK"):
                    klubova_akce = 1
                    zlm_condition_met = True
        
        # LOGIKA PRO KLUBovou akci - Krok 3: Kontrola prefixu ID
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
            st.write(f"- `Podmínka 1 (KEN Sloupec H)`: Nalezená hodnota je **'{ken_sloupec_h}'**. Podmínka (číselně == 1) je **{'splněna' if is_ken_h_one else 'nesplněna'}**.")
            
            # Podmínka 2
            if not zlm_klub_info_values:
                msg = "Pro SAPID kódy nebyly v ZLM nalezeny žádné relevantní záznamy."
            else:
                msg = f"Nalezené hodnoty v ZLM sloupci M: {', '.join(zlm_klub_info_values)}."
            st.write(f"- `Podmínka 2 (ZLM Sloupec M)`: {msg} Podmínka (začíná na 'MK') je **{'splněna' if zlm_condition_met else 'nesplněna'}**.")

            # Podmínka 3
            st.write(f"- `Podmínka 3 (ID dlaždice)`: Hodnota je **'{slug}'**. Podmínka (`začíná na 'sk'`) je **{'splněna' if slug.startswith('sk') else 'nesplněna'}**.")
            
            st.success(f"-> **FINÁLNÍ HODNOTA pro Sloupec B bude: `{klubova_akce}`**")
            
            # Diagnostika SAPID kódů
            st.write(f"- `SAPID kódy nalezené pro ID dlaždice '{id_dlazdice}'`: {sapid_list if sapid_list else 'žádné'}")
            st.write(f"- `Vygenerované kódy zboží`: {len(kody_zbozi)} kódů")
        
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

st.title("Generátor marketingových akcí - SAPID verze")
st.write("Nahrajte 3 požadované soubory ve formátu XLSX (podporuje až desítky tisíc řádků):")

# Použití obecného typu souboru místo specifikace přípony
vazby_produktu_file = st.file_uploader("1. Soubor VAZBY produktu (obsahuje SAPID kódy)", type="xlsx", help="Excel soubor s vazbami produktů - sloupec A obsahuje SAPID kódy")
vazby_akci_file = st.file_uploader("2. Soubor KEN (vazby akcí)", type="xlsx", help="Excel soubor s vazbami akcí")
zlm_file = st.file_uploader("3. Soubor ZLM (obsahuje SAPID kódy)", type="xlsx", help="Excel soubor ZLM - sloupec A obsahuje SAPID kódy")

st.markdown("---")
st.warning("⚠️ Zapnutí plné diagnostiky může výrazně zpomalit zpracování u velkých souborů a zahltit obrazovku výpisy.")
full_diagnostics_checkbox = st.checkbox("Zobrazit detailní diagnostiku pro každý řádek")

if st.button("Spustit generování s SAPID kódy"):
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
                    # UPRAVENO: Přidání 2 hodin pro letní čas
                    letni_cas = datetime.now() + timedelta(hours=2)
                    timestamp = letni_cas.strftime('%d.%m.%Y %H:%M')
                    filename_timestamp = letni_cas.strftime('%Y%m%d_%H%M')
                    
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

# Aktualizované expander bloky
with st.expander("🔧 Informace o SAPID verzi"):
    st.write("""
    **Změny v SAPID verzi:**
    
    **Nová struktura dat:**
    - **Soubor VAZBY produktu**: Sloupec A nyní obsahuje SAPID kódy (dříve OBICIS)
    - **Soubor ZLM**: Sloupec A nyní obsahuje SAPID kódy (dříve OBICIS)
    - **Odstraněna složitá normalizace**: Není už potřeba řešit úvodní nuly u OBICIS kódů
    
    **Zjednodušené zpracování:**
    - Přímé párování SAPID kódů mezi soubory
    - Rychlejší zpracování díky odstranění normalizace
    - Menší možnost chyb díky jednodušší logice
    
    **Zachované funkce:**
    - Všechny původní logiky pro klubovou akci
    - Kompletní diagnostika
    - Statistiky zpracování
    """)

with st.expander("🔧 Informace o logice klubové akce"):
    st.write("""
    **Logika pro sloupec B (klubová akce):**
    
    **Sloupec B ve výsledku = 1**, pokud platí JAKÁKOLI z těchto podmínek:
    
    1. **Sloupec H z KEN souboru obsahuje "1"**
        - Přímé označení klubové akce v KEN souboru
    
    2. **ZLM obsahuje "MK" v sloupci M (index 12)**
        - Logika na základě klubové informace v ZLM (nyní pomocí SAPID kódů)
    
    3. **ID dlaždice začíná "sk"**
        - Logika na základě prefixu ID
    
    **Provázání dat pomocí SAPID:**
    - ID dlaždice z KEN → SAPID kódy z VAZBY produktu
    - SAPID kódy → Data z ZLM souboru
    - Výsledné kódy zboží pro finální export
    """)

with st.expander("🕒 Informace o letním času"):
    st.write("""
    **Úprava pro letní čas:**
    
    - K aktuálnímu času se automaticky přidávají 2 hodiny
    - Tato úprava se vztahuje na:
        - Zobrazovaný čas dokončení zpracování
        - Název stahovaného souboru (formát: vysledek_YYYYMMDD_HHMM.csv)
    
    **Příklad:**
    - Systémový čas: 14:30
    - Zobrazený čas: 16:30 (+ 2 hodiny)
    - Název souboru: vysledek_20240715_1630.csv
    """)

with st.expander("📊 Struktura souborů"):
    st.write("""
    **Struktura vstupních souborů:**
    
    **1. VAZBY produktu:**
    - Sloupec A: SAPID kódy
    - Sloupec C: ID dlaždice
    
    **2. KEN (vazby akcí):**
    - Sloupec B: ID dlaždice
    - Sloupec H: Označení klubové akce (1 = klubová akce)
    - Další sloupce: Názvy, data, značky atd.
    
    **3. ZLM:**
    - Sloupec A: SAPID kódy
    - Sloupec B: Kódy zboží
    - Sloupec M: Klubová informace (MK = klubová akce)
    """)
