import pandas as pd
import streamlit as st
import re
from datetime import datetime
import os

# Funkce pro normalizaci textu při porovnávání
def normalize_text(text):
    if not isinstance(text, str):
        text = str(text)
    # Odstranění nadbytečných mezer, převod na malá písmena
    return re.sub(r'\s+', '', text.lower())

# Načtení defaultních souborů z kořenového adresáře
@st.cache_data
def nacti_defaultni_soubory():
    try:
        vzor = pd.read_excel('vzor.xlsx')
        vazby_znacek = pd.read_excel('vazby_znacek.xlsx', dtype={'A': str})
        return vzor, vazby_znacek
    except Exception as e:
        st.error(f"Chyba při načítání defaultních souborů: {e}")
        return None, None

# Hlavní funkce pro zpracování s diagnostikou
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
    
    # DIAGNOSTIKA: Zobrazení struktury souborů
    st.write("**DIAGNOSTIKA - Struktura souborů:**")
    st.write(f"Vazby produktu - sloupce: {list(vazby_produktu.columns)}")
    st.write(f"Vazby akcí - sloupce: {list(vazby_akci.columns)}")
    st.write(f"ZLM - sloupce: {list(zlm.columns)}")
    st.write(f"Počet řádků - Vazby produktu: {len(vazby_produktu)}, Vazby akcí: {len(vazby_akci)}, ZLM: {len(zlm)}")
    
    for index, radek_akce in vazby_akci.iterrows():
        st.write(f"\n**ZPRACOVÁNÍ ŘÁDKU {index + 1}:**")
        
        novy_radek = {}
        id_dlazdice = radek_akce.iloc[1]
        st.write(f"ID dlaždice: {id_dlazdice}")
        
        # Získání kódů zboží s diagnostikou
        filtrovane_radky = vazby_produktu[vazby_produktu.iloc[:, 2] == id_dlazdice]
        st.write(f"Počet filtrovaných řádků v 'vazby produktu': {len(filtrovane_radky)}")
        
        if len(filtrovane_radky) == 0:
            st.warning(f"⚠️ Nenalezeny žádné řádky v 'vazby produktu' pro ID dlaždice: {id_dlazdice}")
            st.write(f"Dostupné hodnoty ve 3. sloupci 'vazby produktu': {vazby_produktu.iloc[:, 2].unique()[:10]}...")
        
        obicis_list = filtrovane_radky.iloc[:, 0].tolist()
        st.write(f"OBICIS seznam: {obicis_list}")
        
        kody_zbozi = []
        for obicis in obicis_list:
            st.write(f"  Zpracovávám OBICIS: {obicis}")
            radky_zlm = zlm[zlm.iloc[:, 2] == obicis]
            st.write(f"    Nalezeno řádků v ZLM: {len(radky_zlm)}")
            
            if len(radky_zlm) == 0:
                st.warning(f"    ⚠️ Nenalezen žádný řádek v ZLM pro OBICIS: {obicis}")
                st.write(f"    Dostupné hodnoty ve 3. sloupci ZLM: {zlm.iloc[:, 2].unique()[:10]}...")
            
            if not radky_zlm.empty:
                raw_kod = radky_zlm.iloc[0, 1]
                st.write(f"    Surový kód z ZLM: {raw_kod}")
                kod_zbozi = str(raw_kod).split('.')[0].zfill(18)
                st.write(f"    Zpracovaný kód: {kod_zbozi}")
                kody_zbozi.append(kod_zbozi)
        
        st.write(f"Finální kódy zboží: {kody_zbozi}")
        
        # Klubová akce
        klubova_akce = 0
        for obicis in obicis_list:
            radky_zlm = zlm[zlm.iloc[:, 2] == obicis]
            if not radky_zlm.empty and str(radky_zlm.iloc[0, 12]).strip().upper().startswith("MK"):
                klubova_akce = 1
                break
        
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
        
        st.write(f"**Hodnota posledního sloupce: '{','.join(kody_zbozi)}'**")
        
        vysledek = pd.concat([vysledek, pd.DataFrame([novy_radek])], ignore_index=True)
    
    return vysledek

# Streamlit UI
st.title("Generátor marketingových akcí - Diagnostická verze")
st.write("Nahrajte 3 požadované soubory ve formátu XLSX:")

# Použití obecného typu souboru místo specifikace přípony
vazby_produktu_file = st.file_uploader("1. Soubor VAZBY produktu", type=None)
vazby_akci_file = st.file_uploader("2. Soubor KEN (vazby akcí)", type=None)
zlm_file = st.file_uploader("3. Soubor ZLM", type=None)

if st.button("Spustit generování s diagnostikou"):
    if all([vazby_produktu_file, vazby_akci_file, zlm_file]):
        try:
            with st.spinner('Zpracovávám data...'):
                # Kontrola, zda soubory mají správnou příponu .xlsx (case-insensitive)
                for file, name in [(vazby_produktu_file, "VAZBY produktu"), 
                                  (vazby_akci_file, "KEN (vazby akcí)"), 
                                  (zlm_file, "ZLM")]:
                    _, ext = os.path.splitext(file.name)
                    if ext.lower() != '.xlsx':
                        st.error(f"Soubor {name} nemá příponu .xlsx. Nahrajte prosím správný formát souboru.")
                        st.stop()
                
                vazby_produktu = pd.read_excel(vazby_produktu_file)
                vazby_akci = pd.read_excel(vazby_akci_file)
                zlm = pd.read_excel(zlm_file)
                
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
        except Exception as e:
            st.error(f"Došlo k chybě: {str(e)}")
            # Přidáno detailní zobrazení chyby
            import traceback
            st.error(f"Detaily chyby: {traceback.format_exc()}")
    else:
        st.warning("Prosím, nahrajte všechny požadované soubory!")
