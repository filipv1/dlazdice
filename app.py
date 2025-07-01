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
    
    # UPRAVENÝ Index pro ZLM s normalizací OBICIS kódů
    zlm_dict = {}
    zlm_dict_original = {}  # Zachováme i originální klíče pro diagnostiku
    duplicity_count = 0
    
    for _, row in zlm.iterrows():
        # Normalizujeme klíč - převedeme na string a odstraníme mezery
        key_raw = row.iloc[2]
        if pd.isna(key_raw):
            continue
            
        # Převedeme na string a normalizujeme
        key_original = str(key_raw).strip()
        key_normalized = normalize_obicis(key_original)
        
        # Pokud už normalizovaný klíč existuje, počítáme duplicity
        if key_normalized in zlm_dict:
            duplicity_count += 1
            st.write(f"⚠️ Duplicitní OBICIS: {key_original} -> {key_normalized} (použije se první výskyt)")
            continue
            
        kod_zbozi = str(row.iloc[1])  # Kód zboží
        klubova_info = str(row.iloc[12]) if len(row) > 12 else ""  # Klubová informace
        
        # Uložíme pod normalizovaný klíč
        zlm_dict[key_normalized] = {
            'kod_zbozi': kod_zbozi,
            'klubova_info': klubova_info,
            'original_key': key_original
        }
        
        # Uložíme i originální klíč pro diagnostiku
        zlm_dict_original[key_original] = key_normalized
    
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
    st.write(f"Ukázka originálních klíčů z ZLM: {list(zlm_dict_original.keys())[:10]}")
    st.write(f"Ukázka normalizovaných klíčů z ZLM: {list(zlm_dict.keys())[:10]}")
    
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
        
        # NOVÁ LOGIKA: Kontrola sloupce H z KEN souboru (index 7)
        ken_sloupec_h = str(radek_akce.iloc[7]).strip() if len(radek_akce) > 7 else ""
        
        if ken_sloupec_h == "1":
            klubova_akce = 1
            if index < 3:
                st.write(f"✅ Klubová akce nastavena na 1 - sloupec H z KEN obsahuje '1'")
        
        for obicis in obicis_list:
            # Normalizujeme OBICIS pro vyhledávání
            obicis_original = str(obicis).strip()
            obicis_normalized = normalize_obicis(obicis_original)
            
            if index < 3:
                st.write(f"  Zpracovávám OBICIS: '{obicis_original}' -> normalizováno: '{obicis_normalized}'")
            
            zlm_data = zlm_dict.get(obicis_normalized)
            
            if zlm_data:
                raw_kod = zlm_data['kod_zbozi']
                klubova_info = zlm_data['klubova_info']
                original_key = zlm_data['original_key']
                
                if index < 3:
                    st.write(f"    ✅ Nalezen v ZLM! Originální klíč: '{original_key}', Surový kód: '{raw_kod}'")
                
                # Zpracování kódu zboží
                kod_zbozi = str(raw_kod).split('.')[0].zfill(18)
                kody_zbozi.append(kod_zbozi)
                
                if index < 3:
                    st.write(f"    Zpracovaný kód: '{kod_zbozi}'")
                
                # Kontrola klubové akce z ZLM
                if klubova_info.strip().upper().startswith("MK"):
                    klubova_akce = 1
                    if index < 3:
                        st.write(f"    ✅ Klubová akce nastavena na 1 - ZLM obsahuje 'MK' pro OBICIS: {obicis_normalized}")
            else:
                if index < 3:
                    st.warning(f"    ⚠️ Nenalezen záznam v ZLM pro OBICIS: '{obicis_normalized}' (originál: '{obicis_original}')")
                    # Zkusíme najít podobné klíče
                    podobne_klice = [k for k in list(zlm_dict.keys())[:50] if obicis_normalized in k or k in obicis_normalized]
                    if podobne_klice:
                        st.write(f"    Podobné normalizované klíče nalezené: {podobne_klice[:5]}")
                    else:
                        st.write(f"    Žádné podobné klíče nenalezeny")
                        st.write(f"    Typ hledaného klíče: {type(obicis_normalized)}, délka: {len(obicis_normalized)}")
                        st.write(f"    Prvních 10 normalizovaných klíčů v ZLM: {list(zlm_dict.keys())[:10]}")
        
        # Určení hodnoty pro sloupec D na základě slugu
        slug = str(id_dlazdice).lower()

        # Kontrola ID začínajícího na 'sk'
        if slug.startswith("sk"):
            klubova_akce = 1
            if index < 3:
                st.write(f"✅ Klubová akce nastavena na 1 - ID začíná 'sk'")
        
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
        
        if index < 3:
            st.write(f"Finální kódy zboží: {kody_zbozi}")
            st.write(f"Finální hodnota klubová akce: {klubova_akce}")
            st.write(f"Sloupec H z KEN: '{ken_sloupec_h}'")
        
        # ID značky s normalizací textu
        nazev_znacky = radek_akce.iloc[6]
        normalized_nazev = normalize_text(nazev_znacky)
        id_znacky = normalized_vazby_znacek.get(normalized_nazev, "")
        
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
            vzor.columns[1]: klubova_akce,  # UPRAVENÁ LOGIKA - může být 1 z více důvodů
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

st.title("Generátor marketingových akcí - Upravená verze s novou logikou klubové akce")
st.write("Nahrajte 3 požadované soubory ve formátu XLSX (podporuje až desítky tisíc řádků):")

# Zvýšený limit pro upload souborů
max_upload_size = 200  # MB
st.write(f"Maximální velikost souboru: {max_upload_size} MB")

# Použití obecného typu souboru místo specifikace přípony
vazby_produktu_file = st.file_uploader("1. Soubor VAZBY produktu", type=None, help="Excel soubor s vazbami produktů")
vazby_akci_file = st.file_uploader("2. Soubor KEN (vazby akcí)", type=None, help="Excel soubor s vazbami akcí")
zlm_file = st.file_uploader("3. Soubor ZLM", type=None, help="Excel soubor ZLM (může obsahovat tisíce řádků)")

if st.button("Spustit generování s upravenou logikou klubové akce"):
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
                    st.write(f"- Řádky s klubovou akcí (sloupec B = 1): {len(vysledek[vysledek.iloc[:, 1] == 1])}")
                    
        except Exception as e:
            st.error(f"Došlo k chybě: {str(e)}")
            # Přidáno detailní zobrazení chyby
            import traceback
            st.error(f"Detaily chyby: {traceback.format_exc()}")
    else:
        st.warning("Prosím, nahrajte všechny požadované soubory!")

# Přidáme informace o nové logice
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
