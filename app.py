import pandas as pd
import streamlit as st
import re
from datetime import datetime
import os

# Function to debug file uploaders
def debug_file_info(file):
    if file is not None:
        st.text(f"File name: {file.name}")
        st.text(f"File type: {file.type}")
        st.text(f"File size: {file.size} bytes")
        # Extract extension from filename
        _, ext = os.path.splitext(file.name)
        st.text(f"File extension: {ext}")
    else:
        st.text("No file uploaded")

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

# Hlavní funkce pro zpracování
def zpracuj_soubory(vazby_produktu, vazby_akci, zlm):
    vzor, vazby_znacek = nacti_defaultni_soubory()
    if vzor is None or vazby_znacek is None:
        return None

    vysledek = pd.DataFrame(columns=vzor.columns)
    
    for _, radek_akce in vazby_akci.iterrows():
        novy_radek = {}
        id_dlazdice = radek_akce.iloc[1]
        
        # Získání kódů zboží
        filtrovane_radky = vazby_produktu[vazby_produktu.iloc[:, 2] == id_dlazdice]
        obicis_list = filtrovane_radky.iloc[:, 0].tolist()
        
        kody_zbozi = []
        for obicis in obicis_list:
            radky_zlm = zlm[zlm.iloc[:, 2] == obicis]
            if not radky_zlm.empty:
                kod_zbozi = str(radky_zlm.iloc[0, 1]).split('.')[0].zfill(18)
                kody_zbozi.append(kod_zbozi)
        
        # Klubová akce
        klubova_akce = 0
        for obicis in obicis_list:
            radky_zlm = zlm[zlm.iloc[:, 2] == obicis]
            if not radky_zlm.empty and str(radky_zlm.iloc[0, 12]).strip().upper().startswith("MK"):
                klubova_akce = 1
                break
        
        # ID značky
        nazev_znacky = radek_akce.iloc[6]
        znacka_radky = vazby_znacek[vazby_znacek.iloc[:, 2].str.lower() == nazev_znacky.lower()]
        id_znacky = znacka_radky.iloc[0, 0] if not znacka_radky.empty else ""
        
        # Určení hodnoty pro sloupec D na základě slugu
        slug = str(id_dlazdice).lower()
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
        
        # Sestavení řádku
        novy_radek = {
            vzor.columns[0]: 1,
            vzor.columns[1]: klubova_akce,
            vzor.columns[2]: radek_akce.iloc[5],
            vzor.columns[3]: column_d_value,  # Aplikace nové podmínky
            vzor.columns[4]: radek_akce.iloc[16] if len(radek_akce) > 16 else "",
            vzor.columns[5]: slug,
            vzor.columns[6]: radek_akce.iloc[2],
            vzor.columns[7]: radek_akce.iloc[4],
            vzor.columns[8]: f"{str(id_dlazdice).upper()}.jpg",
            vzor.columns[9]: id_znacky,
            vzor.columns[10]: ','.join(kody_zbozi)
        }
        
        vysledek = pd.concat([vysledek, pd.DataFrame([novy_radek])], ignore_index=True)
    
    return vysledek

# Streamlit UI
st.title("Generátor marketingových akcí")
st.write("Nahrajte 3 požadované soubory ve formátu XLSX:")

# Použití obecného typu souboru místo specifikace přípony
vazby_produktu_file = st.file_uploader("1. Soubor VAZBY produktu", type=None)
vazby_akci_file = st.file_uploader("2. Soubor KEN (vazby akcí)", type=None)
zlm_file = st.file_uploader("3. Soubor ZLM", type=None)

# Debugging informace
if vazby_produktu_file:
    st.text("Informace o souboru VAZBY produktu:")
    debug_file_info(vazby_produktu_file)
if vazby_akci_file:
    st.text("Informace o souboru KEN (vazby akcí):")
    debug_file_info(vazby_akci_file)
if zlm_file:
    st.text("Informace o souboru ZLM:")
    debug_file_info(zlm_file)

if st.button("Spustit generování"):
    if all([vazby_produktu_file, vazby_akci_file, zlm_file]):
        try:
            with st.spinner('Zpracovávám data...'):
                # Kontrola, zda soubory mají správnou příponu .xlsx
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
                    timestamp = datetime.now().strftime('%d.%m.%Y 23:59')
                    filename_timestamp = datetime.now().strftime('%Y%m%d_%H%M')
                    
                    csv = vysledek.to_csv(index=False, sep=';', encoding='utf-8-sig')
                    st.success(f"Generování úspěšně dokončeno! (Datum a čas: {timestamp})")
                    st.download_button(
                        label="Stáhnout výsledný soubor",
                        data=csv,
                        file_name=f"vysledek_{filename_timestamp}.csv",
                        mime="text/csv"
                    )
        except Exception as e:
            st.error(f"Došlo k chybě: {str(e)}")
    else:
        st.warning("Prosím, nahrajte všechny požadované soubory!")
