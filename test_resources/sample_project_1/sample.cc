#include "sample.h"

#include <iostream>

namespace sample {


void Foo::Print() const {
    std::cout << "Numbers:";
    for (int i : numbers_) {
        std::cout << ' ' << i;
    }
    std::cout << '\n';
}


}  // namespace sample
