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
                except:
                    # Pokud ne, necháme jako string
                    pass
        
        st.success(f"Úspěšně načten soubor {file_name}: {len(df)} řádků, {len(df.columns)} sloupců")
        return df
        
    except Exception as e:
        st.error(f"Chyba při načítání souboru {file_name}: {e}")
        return None

# Optimalizovaná hlavní funkce pro zpracování
def zpracuj_soubory(vazby_produktu, vazby_akci, zlm):
    vzor, vazby_znacek = nacti_defaultni_soubory()
    if vzor is None or vazby_znacek is None:
        return None

    vysledek = pd.DataFrame(columns=vzor.columns)
    
    # Předpřipravení normalizované tabulky značek pro efektivnější vyhledávání
    normalized_vazby_znacek = {}
    for _, row in vazby_znacek.iterrows():
        normalized_name = normalize_text(row.iloc[2])
        normalized_vazby_znacek[normalized_name] = row.iloc[0]
    
    # OPTIMALIZACE: Vytvoříme indexy pro rychlejší vyhledávání
    st.write("Vytvářím indexy pro rychlejší zpracování...")
    
    # Index pro vazby_produktu (3. sloupec -> 1. sloupec)
    vazby_produktu_dict = {}
    for _, row in vazby_produktu.iterrows():
        # Normalizujeme klíč
        key_raw = row.iloc[2]
        if pd.isna(key_raw):
            continue
        key = str(key_raw).strip()  # ID dlaždice
        
        # Normalizujeme hodnotu
        value_raw = row.iloc[0]
        if pd.isna(value_raw):
            continue
        value = str(value_raw).strip()  # OBICIS
        
        if key not in vazby_produktu_dict:
            vazby_produktu_dict[key] = []
        vazby_produktu_dict[key].append(value)
    
    # Index pro ZLM (3. sloupec -> 2. sloupec a 13. sloupec)
    # Řešíme duplicity - použijeme první výskyt každého OBICIS
    zlm_dict = {}
    duplicity_count = 0
    
    for _, row in zlm.iterrows():
        # Normalizujeme klíč - převedeme na string a odstraníme mezery
        key_raw = row.iloc[2]
        if pd.isna(key_raw):
            continue
            
        # Převedeme na string a normalizujeme
        key = str(key_raw).strip()
        
        # Pokud už klíč existuje, počítáme duplicity
        if key in zlm_dict:
            duplicity_count += 1
            st.write(f"⚠️ Duplicitní OBICIS: {key} (použije se první výskyt)")
            continue
            
        kod_zbozi = str(row.iloc[1])  # Kód zboží
        klubova_info = str(row.iloc[12]) if len(row) > 12 else ""  # Klubová informace
        zlm_dict[key] = {
            'kod_zbozi': kod_zbozi,
            'klubova_info': klubova_info
        }
    
    if duplicity_count > 0:
        st.warning(f"Nalezeno {duplicity_count} duplicitních OBICIS kódů v ZLM souboru!")
    
    st.write(f"Indexy vytvořeny. Vazby produktu: {len(vazby_produktu_dict)} klíčů, ZLM: {len(zlm_dict)} klíčů")
    
    # DIAGNOSTIKA: Zobrazení struktury souborů
    st.write("**DIAGNOSTIKA - Struktura souborů:**")
    st.write(f"Vazby produktu - sloupce: {list(vazby_produktu.columns)}, řádků: {len(vazby_produktu)}")
    st.write(f"Vazby akcí - sloupce: {list(vazby_akci.columns)}, řádků: {len(vazby_akci)}")
    st.write(f"ZLM - sloupce: {list(zlm.columns)}, řádků: {len(zlm)}")
    
    # Ukázka několika ukázkových klíčů z indexů
    st.write(f"Ukázka klíčů z vazby_produktu_dict: {list(vazby_produktu_dict.keys())[:10]}")
    st.write(f"Ukázka klíčů z zlm_dict: {list(zlm_dict.keys())[:10]}")
    
    progress_bar = st.progress(0)
    total_rows = len(vazby_akci)
    
    for index, radek_akce in vazby_akci.iterrows():
        progress_bar.progress((index + 1) / total_rows)
        
        if index < 3:  # Zobrazíme diagnostiku pouze pro první 3 řádky
            st.write(f"\n**ZPRACOVÁNÍ ŘÁDKU {index + 1}:**")
        
        novy_radek = {}
        id_dlazdice_raw = radek_akce.iloc[1]
        if pd.isna(id_dlazdice_raw):
            continue
        id_dlazdice = str(id_dlazdice_raw).strip()  # Normalizujeme ID dlaždice
        
        if index < 3:
            st.write(f"ID dlaždice: '{id_dlazdice}'")
        
        # Získání kódů zboží pomocí optimalizovaných indexů
        obicis_list = vazby_produktu_dict.get(id_dlazdice, [])
        
        if index < 3:
            st.write(f"Nalezené OBICIS kódy: {obicis_list}")
            if not obicis_list:
                st.warning(f"⚠️ Nenalezeny žádné OBICIS kódy pro ID dlaždice: '{id_dlazdice}'")
                st.write(f"Dostupné klíče v vazby_produktu_dict (prvních 20): {list(vazby_produktu_dict.keys())[:20]}")
        
        kody_zbozi = []
        klubova_akce = 0
        
        for obicis in obicis_list:
            # Normalizujeme OBICIS pro vyhledávání
            obicis_normalized = str(obicis).strip()
            
            if index < 3:
                st.write(f"  Zpracovávám OBICIS: '{obicis_normalized}'")
            
            zlm_data = zlm_dict.get(obicis_normalized)
            
            if zlm_data:
                raw_kod = zlm_data['kod_zbozi']
                klubova_info = zlm_data['klubova_info']
                
                if index < 3:
                    st.write(f"    ✅ Nalezen v ZLM! Surový kód: '{raw_kod}'")
                
                # Zpracování kódu zboží
                kod_zbozi = str(raw_kod).split('.')[0].zfill(18)
                kody_zbozi.append(kod_zbozi)
                
                if index < 3:
                    st.write(f"    Zpracovaný kód: '{kod_zbozi}'")
                
                # Kontrola klubové akce
                if klubova_info.strip().upper().startswith("MK"):
                    klubova_akce = 1
            else:
                if index < 3:
                    st.warning(f"    ⚠️ Nenalezen záznam v ZLM pro OBICIS: '{obicis_normalized}'")
                    # Zkusíme najít podobné klíče
                    podobne_klice = [k for k in list(zlm_dict.keys())[:50] if obicis_normalized in k or k in obicis_normalized]
                    if podobne_klice:
                        st.write(f"    Podobné klíče nalezené: {podobne_klice[:5]}")
                    else:
                        st.write(f"    Žádné podobné klíče nenalezeny")
                        st.write(f"    Typ hledaného klíče: {type(obicis_normalized)}, délka: {len(obicis_normalized)}")
                        st.write(f"    Prvních 10 klíčů v ZLM: {list(zlm_dict.keys())[:10]}")
        
        if index < 3:
            st.write(f"Finální kódy zboží: {kody_zbozi}")
        
        # ID značky s normalizací textu
        nazev_znacky = radek_akce.iloc[6]
        normalized_nazev = normalize_text(nazev_znacky)
        id_znacky = normalized_vazby_znacek.get(normalized_nazev, "")
        
        # Určení hodnoty pro sloupec D na základě slugu
        slug = str(id_dlazdice).lower()

        # Add this new block for 'SK' condition
        if slug.startswith("sk"):
            klubova_akce = 1
        
        if slug.startswith("te"):
            column_d_value = "leaflet"
        elif slug.startswith("ma"):
            column_d_value = "magazine"
        elif slug.startswith("dz"):
            column_d_value = "longTermDiscount"
        elif slug.startswith("kp"):
            column_d_value = "coupons"
        else:
            column_d_value = "leaflet"  # Výchozí hodnota
        
        # Zpracování datumu - úprava formátu pro sloupec H
        datum_hodnota = radek_akce.iloc[4]
        
        # Pokud je datum datetime objekt, převedeme ho na formátovaný string
        if isinstance(datum_hodnota, datetime):
            datum_string = datum_hodnota.strftime('%Y-%m-%d')
        else:
            # Pokud je již string nebo jiný typ, zkusíme převést na správný formát
            try:
                if pd.isna(datum_hodnota):
                    datum_string = ""
                else:
                    # Pokud je to string, zkusíme ho přeformátovat
                    datum_obj = pd.to_datetime(datum_hodnota)
                    datum_string = datum_obj.strftime('%Y-%m-%d')
            except:
                # Pokud převod selže, použijeme original jako string
                datum_string = str(datum_hodnota)
        
        # Sestavení hodnoty pro sloupec H ve formátu "YYYY-MM-DD 23:59"
        sloupec_h_hodnota = f"{datum_string} 23:59" if datum_string else ""
        
        novy_radek = {
            vzor.columns[0]: 1,
            vzor.columns[1]: klubova_akce,
            vzor.columns[2]: radek_akce.iloc[5],
            vzor.columns[3]: column_d_value,
            vzor.columns[4]: radek_akce.iloc[16] if len(radek_akce) > 16 else "",
            vzor.columns[5]: slug,
            vzor.columns[6]: radek_akce.iloc[2],
            vzor.columns[7]: sloupec_h_hodnota,  # použití formátovaného data
            vzor.columns[8]: f"{str(id_dlazdice).upper()}.jpg",
            vzor.columns[9]: id_znacky,
            vzor.columns[10]: ','.join(kody_zbozi)
        }
        
        if index < 3:
            st.write(f"**Hodnota posledního sloupce: '{','.join(kody_zbozi)}'**")
        
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

st.title("Generátor marketingových akcí - Optimalizovaná verze pro velké soubory")
st.write("Nahrajte 3 požadované soubory ve formátu XLSX (podporuje až desítky tisíc řádků):")

# Zvýšený limit pro upload souborů
max_upload_size = 200  # MB
st.write(f"Maximální velikost souboru: {max_upload_size} MB")

# Použití obecného typu souboru místo specifikace přípony
vazby_produktu_file = st.file_uploader("1. Soubor VAZBY produktu", type=None, help="Excel soubor s vazbami produktů")
vazby_akci_file = st.file_uploader("2. Soubor KEN (vazby akcí)", type=None, help="Excel soubor s vazbami akcí")
zlm_file = st.file_uploader("3. Soubor ZLM", type=None, help="Excel soubor ZLM (může obsahovat tisíce řádků)")

if st.button("Spustit generování s optimalizací pro velké soubory"):
    if all([vazby_produktu_file, vazby_akci_file, zlm_file]):
        try:
            with st.spinner('Načítám a zpracovávám data (může trvat několik minut pro velké soubory)...'):
                # Kontrola, zda soubory mají správnou příponu .xlsx (case-insensitive)
                for file, name in [(vazby_produktu_file, "VAZBY produktu"), 
                                  (vazby_akci_file, "KEN (vazby akcí)"), 
                                  (zlm_file, "ZLM")]:
                    _, ext = os.path.splitext(file.name)
                    if ext.lower() != '.xlsx':
                        st.error(f"Soubor {name} nemá příponu .xlsx. Nahrajte prosím správný formát souboru.")
                        st.stop()
                
                # Načtení souborů s optimalizací
                vazby_produktu = nacti_velky_excel(vazby_produktu_file, "VAZBY produktu")
                vazby_akci = nacti_velky_excel(vazby_akci_file, "KEN (vazby akcí)")
                zlm = nacti_velky_excel(zlm_file, "ZLM")
                
                if vazby_produktu is None or vazby_akci is None or zlm is None:
                    st.error("Nepodařilo se načíst všechny soubory.")
                    st.stop()
                
                vysledek = zpracuj_soubory(vazby_produktu, vazby_akci, zlm)
                
                if vysledek is not None:
                    # Upravený formát data a času
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
                    
                    # Přidání možnosti zobrazit tabulku s výsledky
                    if st.checkbox("Zobrazit výslednou tabulku"):
                        st.dataframe(vysledek)
                        
                    # Statistiky zpracování
                    st.write("**Statistiky zpracování:**")
                    st.write(f"- Zpracováno řádků: {len(vysledek)}")
                    st.write(f"- Řádky s vyplněnými kódy zboží: {len(vysledek[vysledek.iloc[:, 10] != ''])}")
                    st.write(f"- Řádky bez kódů zboží: {len(vysledek[vysledek.iloc[:, 10] == ''])}")
                    
        except Exception as e:
            st.error(f"Došlo k chybě: {str(e)}")
            # Přidáno detailní zobrazení chyby
            import traceback
            st.error(f"Detaily chyby: {traceback.format_exc()}")
    else:
        st.warning("Prosím, nahrajte všechny požadované soubory!")

# Přidáme informace o optimalizaci
with st.expander("ℹ️ Informace o optimalizaci pro velké soubory"):
    st.write("""
    **Optimalizace pro velké soubory (až 10k+ řádků):**
    
    1. **Indexování dat**: Vytváří se slovníky pro rychlé vyhledávání místo procházení celých tabulek
    2. **Optimalizovaný cache**: Zvýšená kapacita pro ukládání velkých souborů v paměti
    3. **Stringová konzistence**: Všechna ID se převádějí na stringy pro konzistentní porovnávání
    4. **Progress bar**: Zobrazuje průběh zpracování dlouhých operací
    5. **Omezená diagnostika**: Detailní výstup pouze pro první 3 řádky
    6. **Statistiky**: Souhrn úspěšnosti zpracování na konci
    
    **Výkon**: Zpracování 10k řádků by mělo trvat několik sekund až minut místo hodin.
    """)
