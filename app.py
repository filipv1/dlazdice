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
        key_raw = row.iloc[2]
        if pd.isna(key_raw):
            continue
        key = str(key_raw).strip()  # ID dlaždice
        
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
        key_raw = row.iloc[2]
        if pd.isna(key_raw):
            continue
            
        key_original = str(key_raw).strip()
        key_normalized = normalize_obicis(key_original)
        
        if key_normalized in zlm_dict:
            duplicity_count += 1
            st.write(f"⚠️ Duplicitní OBICIS: {key_original} -> {key_normalized} (použije se první výskyt)")
            continue
            
        kod_zbozi = str(row.iloc[1])  # Kód zboží
        klubova_info = str(row.iloc[12]) if len(row) > 12 else ""  # Klubová informace
        
        zlm_dict[key_normalized] = {
            'kod_zbozi': kod_zbozi,
            'klubova_info': klubova_info,
            'original_key': key_original
        }
        
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
        
        obicis_list = vazby_produktu_dict.get(id_dlazdice, [])
        
        if index < 3:
            st.write(f"Nalezené OBICIS kódy: {obicis_list}")
            if not obicis_list:
                st.warning(f"⚠️ Nenalezeny žádné OBICIS kódy pro ID dlaždice: '{id_dlazdice}'")
                st.write(f"Dostupné klíče v vazby_produktu_dict (prvních 20): {list(vazby_produktu_dict.keys())[:20]}")
        
        kody_zbozi = []
        klubova_akce = 0
        
        # LOGIKA PRO KLUBovou akci - Krok 1: Kontrola sloupce H z KEN souboru
        ken_sloupec_h = str(radek_akce.iloc[7]).strip() if len(radek_akce) > 7 else ""
        if ken_sloupec_h == "1":
            klubova_akce = 1
        
        # Zpracování OBICIS kódů a LOGIKA PRO KLUBovou akci - Krok 2: Kontrola ZLM
        for obicis in obicis_list:
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
                
                kod_zbozi = str(raw_kod).split('.')[0].zfill(18)
                kody_zbozi.append(kod_zbozi)
                
                if index < 3:
                    st.write(f"    Zpracovaný kód: '{kod_zbozi}'")
                
                if klubova_info.strip().upper().startswith("MK"):
                    klubova_akce = 1 # Nastaví se na 1, pokud je podmínka splněna
                    if index < 3:
                        st.write(f"    -> ✅ Klubová akce nastavena na 1 - ZLM obsahuje 'MK' pro OBICIS: {obicis_normalized}")
            else:
                if index < 3:
                    st.warning(f"    ⚠️ Nenalezen záznam v ZLM pro OBICIS: '{obicis_normalized}' (originál: '{obicis_original}')")

        # LOGIKA PRO KLUBovou akci - Krok 3: Kontrola prefixu ID dlaždice
        slug = str(id_dlazdice).lower()
        if slug.startswith("sk"):
            klubova_akce = 1

        # Určení hodnoty pro sloupec D na základě slugu
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

        # ####################################################################
        # ## NOVÁ DIAGNOSTIKA: Přehled pro sloupec B (klubová akce) ##
        # ####################################################################
        if index < 3:
            st.markdown("---")
            st.write(f"**DIAGNOSTICKÝ PŘEHLED pro 'klubova_akce' (Sloupec B) pro řádek {index+1}:**")
            
            # Vyhodnocení podmínky 1
            st.write(f"  - `Podmínka 1 (KEN Sloupec H)`: Hodnota je **'{ken_sloupec_h}'**. Podmínka (`== '1'`) je **{'splněna' if ken_sloupec_h == '1' else 'nesplněna'}**.")
            
            # Vyhodnocení podmínky 2
            relevant_mk_info = []
            for obicis in obicis_list:
                obicis_normalized = normalize_obicis(str(obicis).strip())
                zlm_data = zlm_dict.get(obicis_normalized)
                if zlm_data and zlm_data['klubova_info'].strip().upper().startswith("MK"):
                    relevant_mk_info.append(f"'{zlm_data['klubova_info']}' (z OBICIS {obicis_normalized})")
            
            if relevant_mk_info:
                st.write(f"  - `Podmínka 2 (ZLM Sloupec M)`: Nalezeny hodnoty začínající na 'MK': {', '.join(relevant_mk_info)}. Podmínka je **splněna**.")
            else:
                st.write(f"  - `Podmínka 2 (ZLM Sloupec M)`: Nenalezena žádná hodnota začínající na 'MK'. Podmínka je **nesplněna**.")

            # Vyhodnocení podmínky 3
            st.write(f"  - `Podmínka 3 (ID dlaždice)`: Hodnota je **'{slug}'**. Podmínka (`začíná na 'sk'`) je **{'splněna' if slug.startswith('sk') else 'nesplněna'}**.")
            
            st.success(f"  - **FINÁLNÍ HODNOTA pro Sloupec B bude: `{klubova_akce}`**")
            st.markdown("---")

        # ID značky s normalizací textu
        nazev_znacky = radek_akce.iloc[6]
        normalized_nazev = normalize_text(nazev_znacky)
        id_znacky = normalized_vazby_znacek.get(normalized_nazev, "")
        
        # Zpracování datumu - úprava formátu pro sloupec H
        datum_hodnota = radek_akce.iloc[4]
        if isinstance(datum_hodnota, datetime):
            datum_string = datum_hodnota.strftime('%Y-%m-%d')
        else:
            try:
                if pd.isna(datum_hodnota):
                    datum_string = ""
                else:
                    datum_obj = pd.to_datetime(datum_hodnota)
                    datum_string = datum_obj.strftime('%Y-%m-%d')
            except:
                datum_string = str(datum_hodnota)
        
        sloupec_h_hodnota = f"{datum_string} 23:59" if datum_string else ""
        
        novy_radek = {
            vzor.columns[0]: 1,
            vzor.columns[1]: klubova_akce,  # Použití finální hodnoty
            vzor.columns[2]: radek_akce.iloc[5],
            vzor.columns[3]: column_d_value,
            vzor.columns[4]: radek_akce.iloc[16] if len(radek_akce) > 16 else "",
            vzor.columns[5]: slug,
            vzor.columns[6]: radek_akce.iloc[2],
            vzor.columns[7]: sloupec_h_hodnota,
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
