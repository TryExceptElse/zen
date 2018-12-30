#include <iostream>
using namespace std;

// One function works for all data types. This would work
// even for user defined types if operator '>' is overloaded
template <typename T>
T custom_max(T x, T y)
{
    return (x > y)? x: y;
}

int main()
{
    cout << custom_max<int>(1, 2) << endl;
    cout << custom_max<double>(1.0, 2.0) << endl;
    cout << custom_max<char>('a', 'b') << endl;

    return 0;
}
