import csv

# Definición de columnas exactas solicitadas por el usuario:
# - drama (nombre de la serie)
# - capitulo (número)
# - resumen_corto (2 o 3 frases con lo que pasa)
# - giros (qué pasa en cada giro, separado por ;)
# - tipo_giro (traición, secreto, accidente, muerte, venganza, confrontación, romance o revelación)
# - momento (inicio, mitad o final)
# - gancho_final (cómo termina el capítulo para que veas el siguiente)
# - personajes_clave (quiénes participan en el giro)

records = [
    # =========================================================================
    # 1. THE WORLD OF THE MARRIED (Corea del Sur) - Estructura de Thriller / Venganza
    # =========================================================================
    {
        "drama": "The World of the Married",
        "capitulo": 1,
        "resumen_corto": "Ji Seon-u tiene una vida y carrera médica aparentemente idílicas junto a su esposo Tae-oh. Al hallar un cabello pelirrojo en la bufanda de él, comienza a sospechar de una infidelidad sistemática. Durante la fiesta de cumpleaños de Tae-oh descubre un celular escondido en la cajuela de su auto con fotos íntimas de su vecina y una joven desconocida.",
        "giros": "Seon-u encuentra fotos que confirman que todos sus amigos sabían del engaño y lo encubrían; descubre que la amante es Da-kyung",
        "tipo_giro": "traición",
        "momento": "final",
        "gancho_final": "Seon-u toma unas tijeras quirúrgicas con rabia y camina decidida hacia Tae-oh en medio de la fiesta.",
        "personajes_clave": "Ji Seon-u, Lee Tae-oh, Yeo Da-kyung"
    },
    {
        "drama": "The World of the Married",
        "capitulo": 2,
        "resumen_corto": "Seon-u contiene su impulso inicial y decide investigar en secreto para no perder la custodia de su hijo. La amante Da-kyung acude sorpresivamente a su clínica como paciente sin saber que Seon-u ya conoce la verdad. La prueba médica revela que Da-kyung está embarazada de Tae-oh.",
        "giros": "Da-kyung confiesa con cinismo su aventura con un hombre casado; la prueba de embarazo sale positiva frente a Seon-u",
        "tipo_giro": "revelación",
        "momento": "mitad",
        "gancho_final": "Seon-u envía un mensaje directo a su colega traidora ordenándole que le informe a Tae-oh del embarazo.",
        "personajes_clave": "Ji Seon-u, Yeo Da-kyung, Dr. Sul Myung-sook"
    },
    {
        "drama": "The World of the Married",
        "capitulo": 3,
        "resumen_corto": "Tae-oh entra en pánico ante el embarazo pero se niega a confesar la verdad a su esposa. Seon-u revisa los estados bancarios familiares y descubre que su esposo hipotecó la casa y vació los ahorros de su hijo. Durante el funeral de la madre de Tae-oh, él escapa para verse a solas con Da-kyung.",
        "giros": "Descubrimiento de quiebra financiera provocada por el esposo; Seon-u sorprende a Tae-oh besándose con la amante durante el funeral de su madre",
        "tipo_giro": "traición",
        "momento": "final",
        "gancho_final": "Seon-u confirma que Tae-oh no tiene redención y contrata formalmente a un espía para ejecutar su ruina legal.",
        "personajes_clave": "Ji Seon-u, Lee Tae-oh, Min Hyun-seo"
    },
    {
        "drama": "The World of the Married",
        "capitulo": 5,
        "resumen_corto": "Seon-u arma una trampa impecable invitándose a cenar en casa de los influyentes padres de Da-kyung. Durante la cena de gala, revela con calma implacable el embarazo de Da-kyung y la infidelidad de Tae-oh ante toda la familia. Se desata una pelea física y el caos social destruye la reputación de ambos.",
        "giros": "Seon-u desenmascara la aventura frente a los padres ultraconservadores de la amante; Da-kyung golpea a Seon-u en la nuca frente a todos",
        "tipo_giro": "confrontación",
        "momento": "final",
        "gancho_final": "Tae-oh le grita a Seon-u que amar a dos mujeres no es un crimen, sellando su guerra a muerte.",
        "personajes_clave": "Ji Seon-u, Lee Tae-oh, Yeo Da-kyung, Yeo Byung-gyu"
    },
    {
        "drama": "The World of the Married",
        "capitulo": 8,
        "resumen_corto": "Dos años después del divorcio, Tae-oh regresa a la ciudad inmensamente rico y casado con Da-kyung buscando venganza. Seon-u comienza a ser acechada en su casa por un atacante contratado en la oscuridad. Un intruso encapuchado entra a su domicilio y la golpea brutalmente.",
        "giros": "El atacante violento resulta ser un matón contratado en secreto por su exesposo para aterrorizarla y quitarle al hijo",
        "tipo_giro": "venganza",
        "momento": "final",
        "gancho_final": "El doctor Yoon-gi llega al rescate y encuentra a Seon-u ensangrentada en el piso mientras el agresor huye.",
        "personajes_clave": "Ji Seon-u, Lee Tae-oh, Kim Yoon-gi, Park In-gyu"
    },

    # =========================================================================
    # 2. CRASH LANDING ON YOU (Corea del Sur) - Estructura de Aventura / Romance de Riesgo
    # =========================================================================
    {
        "drama": "Crash Landing on You",
        "capitulo": 1,
        "resumen_corto": "La heredera chaebol Yoon Se-ri sale a probar un equipo de parapente cuando un tornado repentino la arrastra a través de la frontera. Despierta colgada de un árbol en plena Zona Desmilitarizada norcoreana frente al capitán Ri Jeong-hyeok. Al intentar huir en dirección errónea, termina internándose aún más en un pueblo militar del norte.",
        "giros": "El tornado desvía a la protagonista a territorio enemigo; el capitán decide no dispararle y la oculta en el último segundo",
        "tipo_giro": "accidente",
        "momento": "inicio",
        "gancho_final": "Un camión militar con tropas enemigas patrulla la aldea y Jeong-hyeok jala a Se-ri a su portón para salvarla.",
        "personajes_clave": "Yoon Se-ri, Ri Jeong-hyeok"
    },
    {
        "drama": "Crash Landing on You",
        "capitulo": 2,
        "resumen_corto": "Jeong-hyeok y sus cuatro soldados de confianza acuerdan ayudar a Se-ri a escapar para evitar ser ejecutados por negligencia. Mientras el capitán viaja a Pyongyang a investigar sospechas de corrupción, la policía militar realiza una inspección sorpresa en el pueblo. El comandante corrupto Cheol-gang descubre a Se-ri escondida en el almacén de kimchis.",
        "giros": "El villano Cheol-gang acorrala a Se-ri con una pistola; Jeong-hyeok llega a toda velocidad en un auto de alto rango diplomático",
        "tipo_giro": "confrontación",
        "momento": "final",
        "gancho_final": "Frente a todo el escuadrón y el pueblo, Jeong-hyeok declara en voz alta que Se-ri es su prometida secreta.",
        "personajes_clave": "Ri Jeong-hyeok, Yoon Se-ri, Cho Cheol-gang"
    },
    {
        "drama": "Crash Landing on You",
        "capitulo": 6,
        "resumen_corto": "Se organiza un plan para que Se-ri viaje al aeropuerto como atleta suplente y pueda abordar un vuelo a Europa. En el trayecto por carretera desierta, camiones blindados de choque pesados enviados por Cheol-gang los emboscan para matarla. Jeong-hyeok aparece en una motocicleta modificada y abre fuego contra los atacantes.",
        "giros": "Jeong-hyeok se interpone como escudo humano y recibe un impacto de bala en la espalda para proteger a Se-ri",
        "tipo_giro": "accidente",
        "momento": "final",
        "gancho_final": "Se-ri debe decidir entre tomar el vuelo que la salvará o perder su escape para llevar a Jeong-hyeok agonizante al hospital.",
        "personajes_clave": "Ri Jeong-hyeok, Yoon Se-ri, Cho Cheol-gang"
    },
    {
        "drama": "Crash Landing on You",
        "capitulo": 10,
        "resumen_corto": "Tras múltiples sacrificios, Se-ri logra cruzar la frontera y regresa triunfante a Seúl justo cuando su codiciosa familia declaraba su muerte legal. Mientras tanto en el norte, Cheol-gang escapa de prisión jurando cruzar a Corea del Sur para asesinarla. Jeong-hyeok descubre el plan y emprende un viaje clandestino por túneles mineros abandonados.",
        "giros": "El villano y el héroe se infiltran independientemente en territorio de Seúl; encuentro nocturno en plena calle nevada de Gangnam",
        "tipo_giro": "romance",
        "momento": "final",
        "gancho_final": "Se-ri camina aturdida por Seúl y se detiene en seco al ver a Jeong-hyeok parado frente a ella diciéndole que la estuvo buscando.",
        "personajes_clave": "Yoon Se-ri, Ri Jeong-hyeok, Cho Cheol-gang"
    },
    {
        "drama": "Crash Landing on You",
        "capitulo": 13,
        "resumen_corto": "Jeong-hyeok y sus soldados disfrutan de una tregua temporal en Seúl protegiendo a Se-ri. Sin embargo, el hermano de Se-ri se alía con Cheol-gang y tienden una emboscada mortal en un almacén portuario. Durante el tiroteo final entre las tropas norcoreanas y los mercenarios, Cheol-gang apunta a traición contra Jeong-hyeok.",
        "giros": "Se-ri embiste su automóvil contra la línea de fuego y recibe una bala en el torso que iba dirigida al capitán",
        "tipo_giro": "accidente",
        "momento": "final",
        "gancho_final": "Jeong-hyeok sostiene a Se-ri inconsciente y bañada en sangre mientras grita desconsolado pidiendo ayuda.",
        "personajes_clave": "Yoon Se-ri, Ri Jeong-hyeok, Cho Cheol-gang, Yoon Se-hyeong"
    },

    # =========================================================================
    # 3. TERESA (México) - Estructura de Ambición, Manipulación y Escalada Social
    # =========================================================================
    {
        "drama": "Teresa",
        "capitulo": 1,
        "resumen_corto": "Teresa Chávez es una hermosa y brillante estudiante de preparatoria que desprecia con fervor la vecindad humilde donde vive. Mantiene un noviazgo con Mariano, un mecánico que sueña con ser médico pero carece de dinero. En su graduación, sufre la humillación pública de sus compañeras ricas al descubrirse que vive en un barrio pobre.",
        "giros": "El pretendiente adinerado la abandona al saber su origen humilde; Teresa jura ante el espejo que nunca volverá a ser humillada",
        "tipo_giro": "revelación",
        "momento": "final",
        "gancho_final": "Teresa pronuncia su icónica promesa: 'Entre ser o no ser, yo soy', decidida a usar su belleza para escalar a cualquier costo.",
        "personajes_clave": "Teresa Chávez, Mariano Sánchez, Paulo"
    },
    {
        "drama": "Teresa",
        "capitulo": 25,
        "resumen_corto": "Teresa ingresa como pasante al prestigioso despacho del millonario abogado Arturo de la Barrera, quien paga sus estudios universitarios. Aunque sigue enamorada de Mariano, Teresa calcula meticulosamente despertar los celos y la admiración de Arturo. Aprovecha la vulnerabilidad emocional de su jefe para provocar un beso apasionado en el despacho.",
        "giros": "Teresa rechaza la propuesta de boda humilde de Mariano para no truncar su ascenso social; Arturo confiesa que está enamorado de ella",
        "tipo_giro": "romance",
        "momento": "mitad",
        "gancho_final": "Arturo le propone matrimonio a Teresa con una vida de lujos, mientras Mariano llega al despacho con un ramo de flores.",
        "personajes_clave": "Teresa Chávez, Arturo de la Barrera, Mariano Sánchez"
    },
    {
        "drama": "Teresa",
        "capitulo": 70,
        "resumen_corto": "Teresa ya está casada con Arturo pero el matrimonio enfrenta problemas económicos por malas inversiones. Para colmo, Fernando Moreno, el prometido multimillonario de su mejor amiga Luisa y mejor amigo de Arturo, regresa del extranjero. Teresa percibe la inmensa fortuna de Fernando y traza un plan despiadado para seducirlo.",
        "giros": "Teresa finge ser la confidente de Fernando mientras envenena su mente contra Luisa; logra que Fernando cancele su boda",
        "tipo_giro": "traición",
        "momento": "final",
        "gancho_final": "Fernando rompe su compromiso ante el altar y busca a Teresa en privado para confesarle que daría toda su fortuna por ella.",
        "personajes_clave": "Teresa Chávez, Fernando Moreno, Luisa de la Barrera, Arturo"
    },
    {
        "drama": "Teresa",
        "capitulo": 105,
        "resumen_corto": "Teresa consuma la traición: hace que Fernando le ceda legalmente la mitad de su gigantesca fortuna y rompe con él de inmediato. Sin embargo, su ambición desmedida provoca que su propia madre reniegue de ella y caiga mortalmente enferma. Al descubrir el fraude financiero, Arturo y Mariano se unen para desenmascarar todas sus mentiras.",
        "giros": "La madre de Teresa fallece repudiándola; Fernando y Arturo descubren que Teresa sólo amaba el dinero de ambos",
        "tipo_giro": "muerte",
        "momento": "mitad",
        "gancho_final": "Teresa queda completamente sola en su mansión vacía, abrazando el oso de peluche que le regaló su primer amor.",
        "personajes_clave": "Teresa Chávez, Doña Refugio, Arturo de la Barrera, Fernando Moreno"
    },
    {
        "drama": "Teresa",
        "capitulo": 152,
        "resumen_corto": "En el desenlace culminante, Teresa intenta donar toda la fortuna robada a una fundación para limpiar su nombre y recuperar a Arturo. Al volver a su recámara desolada, Fito, su antiguo cómplice del barrio, entra armado buscando cobrar una vieja venganza. Teresa recibe un disparo pero sobrevive al juicio social y moral de todos.",
        "giros": "Atentado a mano armada contra Teresa en su mansión; arrepentimiento genuino tras perderlo todo",
        "tipo_giro": "confrontación",
        "momento": "final",
        "gancho_final": "Arturo entra a la habitación de Teresa, la levanta del suelo entre lágrimas y le otorga una última oportunidad de redención.",
        "personajes_clave": "Teresa Chávez, Arturo de la Barrera, Fito"
    },

    # =========================================================================
    # 4. RUBÍ (México) - Estructura de Traición Femenina y Belleza Fatal
    # =========================================================================
    {
        "drama": "Rubí",
        "capitulo": 1,
        "resumen_corto": "Rubí Pérez es una universitaria deslumbrante que utiliza la beca de una prestigiosa universidad privada para codearse con la alta sociedad. Se hace pasar por la mejor amiga incondicional de Maribel, una joven adinerada con discapacidad física en una pierna. A través de Maribel conoce a su prometido Héctor Ferrer, un arquitecto inmensamente rico.",
        "giros": "Rubí finge compasión hacia Maribel mientras envidia secretamente su estatus; descubre que el mejor amigo de Héctor, Alejandro, es solo un médico sin fortuna",
        "tipo_giro": "secreto",
        "momento": "final",
        "gancho_final": "Rubí decide rechazar el amor sincero de Alejandro al saber que no es rico y fija su mirada depredadora en Héctor.",
        "personajes_clave": "Rubí Pérez, Maribel de la Fuente, Alejandro Cárdenas, Héctor Ferrer"
    },
    {
        "drama": "Rubí",
        "capitulo": 30,
        "resumen_corto": "Rubí despliega toda su sensualidad y astucia psicológica para desestabilizar la mente de Héctor antes de la boda. Finge dudar entre su moral y su pasión prohibida, citándolo clandestinamente para atormentarlo. El día del enlace nupcial, la iglesia está repleta con la alta sociedad esperando a los novios.",
        "giros": "Héctor huye de la iglesia dejando plantada a Maribel en el altar; escapa en un avión privado hacia Cancún con Rubí",
        "tipo_giro": "traición",
        "momento": "final",
        "gancho_final": "Maribel colapsa en llanto en el atrio con el vestido destrozado mientras Rubí y Héctor brindan con champaña en pleno vuelo.",
        "personajes_clave": "Rubí Pérez, Héctor Ferrer, Maribel de la Fuente, Alejandro Cárdenas"
    },
    {
        "drama": "Rubí",
        "capitulo": 65,
        "resumen_corto": "El matrimonio de Rubí con Héctor se transforma en un infierno de celos enfermizos y maltrato psicológico. Héctor descubre que Rubí sigue obsesionada con Alejandro, quien ahora es un neurocirujano millonario y de fama internacional. La madre de Rubí, Doña Lola, descubre en cartas la magnitud de la maldad de su hija.",
        "giros": "Doña Lola sufre un infarto fulminante al enterarse de la bajeza de Rubí; Héctor encierra a Rubí bajo llave en la mansión",
        "tipo_giro": "muerte",
        "momento": "mitad",
        "gancho_final": "Rubí llora sobre la tumba de su madre jurando venganza contra todos los que intenten quitarle su posición.",
        "personajes_clave": "Rubí Pérez, Doña Lola, Héctor Ferrer, Alejandro Cárdenas"
    },
    {
        "drama": "Rubí",
        "capitulo": 90,
        "resumen_corto": "Rubí queda embarazada pero desconoce si el padre es Héctor o Alejandro debido a un encuentro secreto. Héctor descubre la duda de paternidad y en un arranque de furia desquiciada amenaza con matarla. Durante un forcejeo violento en las escaleras de la mansión, Rubí resbala y cae.",
        "giros": "Caída trágica por las escaleras que le provoca la pérdida del bebé; Héctor es arrestado por agresión física",
        "tipo_giro": "accidente",
        "momento": "final",
        "gancho_final": "Alejandro atiende de emergencia a Rubí en el quirófano y le comunica que nunca más podrá tener hijos.",
        "personajes_clave": "Rubí Pérez, Héctor Ferrer, Alejandro Cárdenas"
    },
    {
        "drama": "Rubí",
        "capitulo": 115,
        "resumen_corto": "En el clímax trágico de la historia, Héctor muere trágicamente y Rubí lo pierde todo por sus fraudes. Al ser acorralada en un puente peatonal acristalado, tropieza, rompe el barandal de cristal y cae al vacío sobre una barandilla metálica. Sobrevive milagrosamente pero con el rostro desfigurado y una pierna amputada.",
        "giros": "Accidente catastrófico que le arrebata la belleza física; adoctrina en secreto a su pequeña sobrina Fernanda para consumar su venganza",
        "tipo_giro": "venganza",
        "momento": "final",
        "gancho_final": "Años después, la sobrina Fernanda, idéntica a Rubí de joven, entra al consultorio de Alejandro y lo seduce con un beso idéntico al de Rubí.",
        "personajes_clave": "Rubí Pérez, Alejandro Cárdenas, Fernanda"
    },

    # =========================================================================
    # 5. LA ROSA DE GUADALUPE (México) - Estructura Autoconclusiva de Tensión y Milagro
    # =========================================================================
    {
        "drama": "La Rosa de Guadalupe",
        "capitulo": 1,
        "resumen_corto": "En el episodio de impacto juvenil, una adolescente brillante cae bajo la influencia de un reto viral de redes sociales manipulado por acosadores escolares. La presión social la lleva a aislarse de su familia y robar medicamentos del botiquín materno. Su madre nota cambios drásticos de comportamiento pero no logra descifrar el origen del secreto.",
        "giros": "La protagonista es inducida a consumir una sobredosis en vivo para ganar popularidad; una compañera arrepentida confiesa la verdad a la madre",
        "tipo_giro": "accidente",
        "momento": "mitad",
        "gancho_final": "La madre reza con desesperación frente a la imagen de la Virgen y de repente aparece una rosa blanca fresca sobre la mesa.",
        "personajes_clave": "Valeria (Hija), Claudia (Madre), Acosadores"
    },
    {
        "drama": "La Rosa de Guadalupe",
        "capitulo": 2,
        "resumen_corto": "Tras la aparición de la rosa, la madre corre a la habitación y encuentra a su hija desmayada y al borde de un paro respiratorio. Los paramédicos logran reanimarla en el hospital gracias a que la madre identificó a tiempo las sustancias consumidas. Con la ayuda de la policía cibernética, se desenmascara la red de acoso estudiantil.",
        "giros": "Reanimación médica exitosa de emergencia; el aire místico sopla sobre el rostro de la joven al despertar y reflexionar",
        "tipo_giro": "revelación",
        "momento": "final",
        "gancho_final": "La protagonista abraza a sus padres entre lágrimas en el auditorio escolar mientras los acosadores son expulsados y procesados.",
        "personajes_clave": "Valeria, Claudia, Autoridades escolares"
    },
    {
        "drama": "La Rosa de Guadalupe",
        "capitulo": 3,
        "resumen_corto": "En un episodio clásico de usurpación familiar, una prima ambiciosa llega de provincia para quedarse temporalmente en casa de sus tíos acomodados. Rápidamente comienza a seducir al novio de su prima bondadosa y a robar pertenencias culpando a la empleada doméstica. La tensión escala cuando la prima buena descubre joyas escondidas en la maleta de la intrusa.",
        "giros": "La prima mala empuja a la prima buena por la ventana para evitar ser delatada; la víctima queda en coma temporal",
        "tipo_giro": "traición",
        "momento": "mitad",
        "gancho_final": "La villana finge llanto desconsolado ante la familia mientras se coloca el anillo robado frente al espejo de la clínica.",
        "personajes_clave": "Lorena (Prima rival), Mariana (Prima noble), Novio"
    },
    {
        "drama": "La Rosa de Guadalupe",
        "capitulo": 4,
        "resumen_corto": "Durante el coma de Mariana, Lorena convence a la familia de apurar el matrimonio con el novio para 'unir el dolor familiar'. La madre sospecha de las actitudes cínicas de Lorena y encuentra la rosa blanca sobre el respirador artificial de su hija. En ese preciso momento, las cámaras de seguridad de la casa vecina revelan el video del empujón premeditado.",
        "giros": "Aparición de prueba irrefutable en video; Mariana despierta del coma señalando directamente a su prima",
        "tipo_giro": "confrontación",
        "momento": "final",
        "gancho_final": "La policía ingresa a la sala justo cuando Lorena intentaba desconectar el soporte vital, siendo arrestada en flagrancia.",
        "personajes_clave": "Mariana, Lorena, Madre, Policía"
    }
]

csv_file_path = "C:/Users/coazo/docu_factory/kdrama_scraper/guia_ritmo_dramas_telenovelas.csv"
fieldnames = [
    "drama",
    "capitulo",
    "resumen_corto",
    "giros",
    "tipo_giro",
    "momento",
    "gancho_final",
    "personajes_clave"
]

with open(csv_file_path, mode="w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    for row in records:
        writer.writerow(row)

print(f"Archivo generado exitosamente con {len(records)} registros en: {csv_file_path}")
