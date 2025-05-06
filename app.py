import pandas as pd
import streamlit as st
import re
from datetime import datetime
import io
import os
import tempfile
import base64

# Konfigurace stránky pro lepší vzhled
st.set_page_config(
    page_title="Generátor marketingových akcí",
    page_icon="📊",
    layout="wide"
)

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

# Pomocná funkce pro bezpečné načtení souboru
# Upraveno pro obejití problému s názvy souborů
def bezpecne_nacteni_excel(uploaded_file):
    if uploaded_file is None:
        return None
    
    try:
        # Načteme přímo z BytesIO objektu bez použití názvu souboru
        bytes_data = uploaded_file.getvalue()
        df = pd.read_excel(io.BytesIO(bytes_data))
        return df
    except Exception as e:
        st.error(f"Chyba při načítání souboru: {e}")
        return None

# Hlavní funkce pro zpracování
def zpracuj_soubory(vazby_produktu, vazby_akci, zlm):
    vzor, vazby_znacek = nacti_defaultni_soubory()
    if vzor is None or vazby_znacek is None:
        return None

    # Ověření datových typů a struktur
    for df, nazev in [(vazby_produktu, "VAZBY produktu"), 
                     (vazby_akci, "KEN (vazby akcí)"), 
                     (zlm, "ZLM")]:
        if df is None or not isinstance(df, pd.DataFrame):
            st.error(f"Soubor {nazev} nebyl správně načten.")
            return None
        if df.empty:
            st.error(f"Soubor {nazev} neobsahuje žádná data.")
            return None

    # Kontrola minimálního počtu sloupců
    if vazby_produktu.shape[1] < 3:
        st.error("Soubor VAZBY produktu nemá dostatečný počet sloupců (očekáváno minimálně 3).")
        return None
    if vazby_akci.shape[1] < 17:
        st.error("Soubor KEN (vazby akcí) nemá dostatečný počet sloupců (očekáváno minimálně 17).")
        return None
    if zlm.shape[1] < 13:
        st.error("Soubor ZLM nemá dostatečný počet sloupců (očekáváno minimálně 13).")
        return None

    # Inicializace výsledného DataFrame
    vysledek = pd.DataFrame(columns=vzor.columns)
    
    # Zpracování dat
    for index, radek_akce in vazby_akci.iterrows():
        try:
            # Bezpečné získání ID dlaždice
            id_dlazdice = radek_akce.iloc[1] if len(radek_akce) > 1 else None
            if pd.isna(id_dlazdice):
                continue
                
            # Získání kódů zboží
            kody_zbozi = []
            try:
                filtrovane_radky = vazby_produktu[vazby_produktu.iloc[:, 2] == id_dlazdice]
                obicis_list = filtrovane_radky.iloc[:, 0].tolist() if not filtrovane_radky.empty else []
                
                for obicis in obicis_list:
                    if pd.isna(obicis):
                        continue
                        
                    radky_zlm = zlm[zlm.iloc[:, 2] == obicis]
                    if not radky_zlm.empty and radky_zlm.shape[1] > 1:
                        kod_hodnota = radky_zlm.iloc[0, 1]
                        if pd.notna(kod_hodnota):
                            kod_zbozi = str(kod_hodnota).split('.')[0].zfill(18)
                            kody_zbozi.append(kod_zbozi)
            except Exception as e:
                st.warning(f"Problém při zpracování kódů zboží pro ID dlaždice {id_dlazdice}: {e}")
            
            # Klubová akce
            klubova_akce = 0
            try:
                for obicis in obicis_list:
                    if pd.isna(obicis):
                        continue
                        
                    radky_zlm = zlm[zlm.iloc[:, 2] == obicis]
                    if not radky_zlm.empty and radky_zlm.shape[1] > 12:
                        znacka_hodnota = radky_zlm.iloc[0, 12]
                        if pd.notna(znacka_hodnota) and str(znacka_hodnota).strip().upper().startswith("MK"):
                            klubova_akce = 1
                            break
            except Exception as e:
                st.warning(f"Problém při určení klubové akce pro ID dlaždice {id_dlazdice}: {e}")
            
            # ID značky
            id_znacky = ""
            try:
                if len(radek_akce) > 6:
                    nazev_znacky = radek_akce.iloc[6]
                    if pd.notna(nazev_znacky):
                        znacka_radky = vazby_znacek[vazby_znacek.iloc[:, 2].str.lower() == str(nazev_znacky).lower()]
                        id_znacky = znacka_radky.iloc[0, 0] if not znacka_radky.empty else ""
            except Exception as e:
                st.warning(f"Problém při určení ID značky pro ID dlaždice {id_dlazdice}: {e}")
            
            # Určení hodnoty pro sloupec D na základě slugu
            slug = str(id_dlazdice).lower() if pd.notna(id_dlazdice) else ""
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
            
            # Bezpečné získání hodnot
            def bezpecny_pristup(dataframe, index, default=""):
                try:
                    if len(dataframe) > index:
                        hodnota = dataframe.iloc[index]
                        return "" if pd.isna(hodnota) else str(hodnota)
                    return default
                except:
                    return default
            
            # Sestavení řádku
            novy_radek = {}
            for i, col in enumerate(vzor.columns):
                if i == 0:
                    novy_radek[col] = 1
                elif i == 1:
                    novy_radek[col] = klubova_akce
                elif i == 2:
                    novy_radek[col] = bezpecny_pristup(radek_akce, 5)
                elif i == 3:
                    novy_radek[col] = column_d_value
                elif i == 4:
                    novy_radek[col] = bezpecny_pristup(radek_akce, 16)
                elif i == 5:
                    novy_radek[col] = slug
                elif i == 6:
                    novy_radek[col] = bezpecny_pristup(radek_akce, 2)
                elif i == 7:
                    novy_radek[col] = bezpecny_pristup(radek_akce, 4)
                elif i == 8:
                    novy_radek[col] = f"{str(id_dlazdice).upper()}.jpg" if pd.notna(id_dlazdice) else ""
                elif i == 9:
                    novy_radek[col] = id_znacky
                elif i == 10:
                    novy_radek[col] = ','.join(kody_zbozi)
                else:
                    novy_radek[col] = ""
            
            # Přidání řádku do výsledku
            vysledek.loc[len(vysledek)] = novy_radek
            
        except Exception as e:
            st.warning(f"Problém při zpracování řádku {index}: {e}")
            continue
    
    if vysledek.empty:
        st.error("Nepodařilo se vygenerovat žádný výstup. Zkontrolujte vstupní data.")
        return None
        
    return vysledek

# Alternativní metoda pro nahrání souborů
def show_uploader_alternative():
    st.write("Alternativní metoda nahrání souborů:")
    
    uploaded_files = {}
    file_types = ["VAZBY produktu", "KEN (vazby akcí)", "ZLM"]
    
    for file_type in file_types:
        uploaded_file = st.file_uploader(f"Soubor {file_type}", type=["xlsx"], key=f"alt_{file_type}")
        uploaded_files[file_type] = uploaded_file
    
    return uploaded_files

# Streamlit UI
st.title("Generátor marketingových akcí")
st.write("Nahrajte 3 požadované soubory ve formátu XLSX:")

# Přidání záložek pro různé metody nahrávání
tab1, tab2 = st.tabs(["Standardní nahrávání", "Alternativní nahrávání"])

with tab1:
    vazby_produktu_file = st.file_uploader("1. Soubor VAZBY produktu", type=["xlsx"], key="std_vazby")
    vazby_akci_file = st.file_uploader("2. Soubor KEN (vazby akcí)", type=["xlsx"], key="std_ken")
    zlm_file = st.file_uploader("3. Soubor ZLM", type=["xlsx"], key="std_zlm")
    
    if st.button("Spustit generování", key="btn_std"):
        if all([vazby_produktu_file, vazby_akci_file, zlm_file]):
            try:
                with st.spinner('Zpracovávám data...'):
                    vazby_produktu = bezpecne_nacteni_excel(vazby_produktu_file)
                    vazby_akci = bezpecne_nacteni_excel(vazby_akci_file)
                    zlm = bezpecne_nacteni_excel(zlm_file)
                    
                    vysledek = zpracuj_soubory(vazby_produktu, vazby_akci, zlm)
                    
                    if vysledek is not None:
                        try:
                            csv = vysledek.to_csv(index=False, sep=';', encoding='utf-8-sig')
                            st.success(f"Generování úspěšně dokončeno! Vytvořeno {len(vysledek)} řádků.")
                            
                            # Příprava tlačítka pro stažení
                            file_name = f"vysledek_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
                            st.download_button(
                                label="Stáhnout výsledný soubor CSV",
                                data=csv,
                                file_name=file_name,
                                mime="text/csv"
                            )
                            
                            # Ukázka prvních 5 řádků výsledku
                            st.write("Náhled výsledků:")
                            st.dataframe(vysledek.head(5))
                        except Exception as e:
                            st.error(f"Chyba při exportu CSV: {str(e)}")
            except Exception as e:
                st.error(f"Došlo k chybě: {str(e)}")
        else:
            st.warning("Prosím, nahrajte všechny požadované soubory!")

with tab2:
    uploaded_files = show_uploader_alternative()
    
    if st.button("Spustit generování", key="btn_alt"):
        if all(uploaded_files.values()):
            try:
                with st.spinner('Zpracovávám data...'):
                    vazby_produktu = bezpecne_nacteni_excel(uploaded_files["VAZBY produktu"])
                    vazby_akci = bezpecne_nacteni_excel(uploaded_files["KEN (vazby akcí)"])
                    zlm = bezpecne_nacteni_excel(uploaded_files["ZLM"])
                    
                    vysledek = zpracuj_soubory(vazby_produktu, vazby_akci, zlm)
                    
                    if vysledek is not None:
                        csv = vysledek.to_csv(index=False, sep=';', encoding='utf-8-sig')
                        st.success(f"Generování úspěšně dokončeno! Vytvořeno {len(vysledek)} řádků.")
                        
                        file_name = f"vysledek_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
                        st.download_button(
                            label="Stáhnout výsledný soubor CSV",
                            data=csv,
                            file_name=file_name,
                            mime="text/csv"
                        )
                        
                        st.write("Náhled výsledků:")
                        st.dataframe(vysledek.head(5))
            except Exception as e:
                st.error(f"Došlo k chybě: {str(e)}")
        else:
            st.warning("Prosím, nahrajte všechny požadované soubory!")

# Přidání instrukcí a informací o aplikaci
with st.expander("Informace o aplikaci"):
    st.write("""
    ### Jak používat aplikaci
    
    1. Nahrajte tři požadované Excel soubory: VAZBY produktu, KEN (vazby akcí) a ZLM.
    2. Klikněte na tlačítko "Spustit generování".
    3. Po úspěšném zpracování si můžete stáhnout výsledný CSV soubor.
    
    ### Řešení problémů
    
    Pokud se při nahrávání souborů objeví chyba, zkuste:
    - Použít druhou záložku "Alternativní nahrávání"
    - Ujistit se, že soubory mají správný formát (XLSX)
    - Zkontrolovat, že soubory obsahují očekávané sloupce
    
    ### Požadavky na vstupní soubory
    
    - **VAZBY produktu**: Obsahuje minimálně 3 sloupce
    - **KEN (vazby akcí)**: Obsahuje minimálně 17 sloupců
    - **ZLM**: Obsahuje minimálně 13 sloupců
    """)
