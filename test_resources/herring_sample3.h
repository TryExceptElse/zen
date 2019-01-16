#include <vector>

namespace sample {


/**
 * Sample class declaration
 */
class Foo {
 public:
  explicit Foo(/*test*/std::vector<int> numbers): numbers_(numbers) {}

  void Print() const;
 private:
  std::vector<int> numbers_;
};

/**
 * Irrelevant, added function definition.
 */
inline std::string RedHerring() { return "Hello"; }

}  // namespace sample
