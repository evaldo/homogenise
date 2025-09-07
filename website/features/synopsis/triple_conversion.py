class TripleConversion:
    def triple_to_paragraph(self, triple_list):
        paragraph = ""
        for (s, p, o) in triple_list:
            fragment = f"{s} {p} {o}"

            if not paragraph: 
                paragraph = fragment
            else:
                paragraph += f", and {fragment}"
        
        paragraph += "."

        return paragraph
