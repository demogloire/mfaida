import csv
import io



#Importation Etagère
def import_csv(file):

    erreur_line=0
    return_data=[]
    decoded_file = file.read().decode('utf-8')
    io_string = io.StringIO(decoded_file)
    reader = csv.reader(io_string, delimiter=';', quotechar='"')
    for row in reader:
        erreur_, data=verification_ligne(row)
        if erreur_ > 0:
            erreur_line=erreur_line+1
        else:
            return_data.append(data)
    return erreur_line, return_data
            


#Verifier si la valeur est 
def is_numeric(s):
    try:
        float(s)
        return True
    except ValueError:
        return False



#Verification des lignes
def verification_ligne(ligne):
    erreur=0
    if len(ligne)<3 or len(ligne)>3:
        erreur=erreur+1
    elif is_numeric(ligne[1]) and is_numeric(ligne[2]):
        if float(ligne[2])==0 or float(ligne[2])==1:
            pass
        else:
            erreur=erreur+1
    else:
        erreur=erreur+1
    
    if erreur > 0:
        return erreur, []
    else:
        return erreur, [ligne[0],abs(int(ligne[1])),abs(int(ligne[2]))]

    